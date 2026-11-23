"""Transaction categorisation.

Predictions always map onto rows of the existing `categories` table
(database/SpendGPT.sql). Categories and category_ids are never invented: the
model predicts a category *name*, which is resolved to the live category_id.

Tiers, tried in order. The first confident answer wins:
  1. history - the same user already has this merchant categorised
  2. rule    - merchant / keyword rules (fast, deterministic, explainable)
  3. ml      - character n-gram TF-IDF + logistic regression, trained on the
               labelled seed transactions and receipt items
  4. llm     - LM Studio, constrained to the category list (optional; off in
               the save paths so saving a transaction never waits on an LLM)
  5. default - "Other" with confidence 0 (callers may leave category_id NULL)

The LLM is not used for routine categorisation: rules + ML handle the known
merchants in microseconds and the LLM only helps with truly unknown text.
"""
import csv
import logging
import re
import threading
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.transaction import Transaction
from app.services.lmstudio_service import LMStudioClient, LMStudioError

logger = logging.getLogger(__name__)

MODEL_VERSION = "tfidf-char-logreg-v1"
SEED_DIR = Path(__file__).resolve().parents[3] / "database"
DEFAULT_CATEGORY = "Other"

RULE_CONFIDENCE = 0.95
HISTORY_CONFIDENCE = 0.9
LLM_CONFIDENCE = 0.7
ML_MIN_PROBABILITY = 0.6
ML_MIN_SAMPLES = 20

# Placeholder merchant names that carry no information (the receipt upload
# stores "Unknown" when OCR cannot read the merchant).
UNKNOWN_MERCHANTS = {"", "unknown", "n a", "na", "none", "null"}

# Keyword rules, keyed by the category_name values seeded in SpendGPT.sql.
# Matched as whole words on normalised text; longer keywords win.
MERCHANT_RULES: dict[str, list[str]] = {
    "Groceries": [
        "aldi", "lidl", "tesco", "dunnes", "supervalu", "centra", "spar", "londis", "mace",
        "costcutter", "iceland", "asian market", "supermarket", "grocery", "groceries",
    ],
    "Rent": ["rent", "landlord", "accommodation", "student residence", "letting agent"],
    "Utilities": [
        "electric ireland", "bord gais", "sse airtricity", "energia", "flogas", "irish water",
        "uisce eireann", "broadband", "virgin media", "eir", "vodafone", "three ireland", "gomo",
        "tesco mobile", "electricity", "gas bill", "phone bill",
    ],
    "Transport": [
        "leap card", "leap", "dublin bus", "bus eireann", "irish rail", "iarnrod", "luas", "dart",
        "aircoach", "uber", "free now", "freenow", "bolt", "taxi", "circle k", "applegreen",
        "maxol", "texaco", "fuel", "petrol", "parking", "toll", "dublinbikes",
    ],
    "Health": [
        "pharmacy", "chemist", "mccabes", "boots", "lloyds pharmacy", "hickeys", "doctor", "gp",
        "dental", "dentist", "optician", "specsavers", "hospital", "clinic", "physio",
        "prescription",
    ],
    "Eating Out": [
        "mcdonalds", "burger king", "kfc", "subway", "supermacs", "eddie rockets", "starbucks",
        "costa", "insomnia", "butlers", "cafe", "coffee", "restaurant", "takeaway", "dominos",
        "apache pizza", "pizza", "deliveroo", "just eat", "uber eats", "nandos", "boojum",
        "chipotle", "five guys", "canteen",
    ],
    "Shopping": [
        "penneys", "primark", "zara", "tk maxx", "river island", "jd sports", "decathlon",
        "amazon", "argos", "ikea", "currys", "harvey norman", "smyths", "dealz", "euro giant",
        "shein", "asos", "ebay", "eason",
    ],
    "Entertainment": [
        "cinema", "cineworld", "omniplex", "odeon", "imc", "steam", "playstation", "xbox",
        "nintendo", "ticketmaster", "concert", "festival", "pub", "nightclub", "bowling",
        "theatre", "museum",
    ],
    "Subscriptions": [
        "netflix", "spotify", "disney", "prime video", "amazon prime", "icloud", "apple com",
        "youtube premium", "google one", "now tv", "crunchyroll", "audible", "subscription",
        "membership", "gym",
    ],
}

# Receipt line items, used when a receipt's merchant could not be read.
ITEM_RULES: dict[str, list[str]] = {
    "Groceries": [
        "milk", "bread", "butter", "eggs", "cheese", "cheddar", "yoghurt", "apples", "bananas",
        "carrots", "potatoes", "onions", "tomatoes", "pasta", "rice", "cereal", "cornflakes",
        "chicken breast", "minced beef", "sausages", "ham", "tuna", "beans", "tea bags",
        "instant coffee", "orange juice", "crisps", "chocolate bar", "frozen pizza", "fruit",
        "vegetables",
    ],
    "Eating Out": [
        "burrito", "nachos", "latte", "cappuccino", "flat white", "hot chocolate", "croissant",
        "toasted sandwich", "burger meal", "chicken fillet meal", "garlic bread", "meal deal",
    ],
    "Health": [
        "paracetamol", "ibuprofen", "plasters", "vitamins", "vitamin", "toothpaste",
        "toothbrush", "sunscreen", "prescription",
    ],
    "Shopping": [
        "hoodie", "jeans", "t shirt", "socks", "running shorts", "headphones", "phone case",
        "usb c cable", "charger", "desk lamp", "yoga mat", "water bottle", "gym bag", "notebook",
    ],
}


@dataclass
class CategoryResult:
    category_id: int | None
    category_name: str | None
    confidence: float
    source: str  # history | rule | ml | llm | default
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


# -- text helpers -------------------------------------------------------------------
def normalize_text(text: str | None) -> str:
    """Lowercase, strip accents and punctuation: "McDonald's #123" -> "mcdonalds 123"."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    text = re.sub(r"['’`]", "", text.lower())
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Tokens that describe the shop, not what was bought ("TESCO STORES 3021 DUBLIN 2").
# Removed before the ML step only: evaluation showed "stores" was being learnt as a
# Groceries signal from "Dunnes Stores". See categorization_eval.py.
GENERIC_MERCHANT_TOKENS = {
    "stores", "store", "ltd", "limited", "plc", "ie", "ireland", "irl", "gmbh", "inc", "co",
    "the", "trip", "dublin", "cork", "galway", "limerick", "express", "metro",
}


def model_text(text: str | None) -> str:
    """Normalised text with generic store tokens and numbers removed (ML features)."""
    tokens = [t for t in normalize_text(text).split() if t not in GENERIC_MERCHANT_TOKENS and not t.isdigit()]
    return " ".join(tokens) or normalize_text(text)


def is_unknown_merchant(merchant: str | None) -> bool:
    return normalize_text(merchant) in UNKNOWN_MERCHANTS


def _compile(rules: dict[str, list[str]]) -> list[tuple[str, str, re.Pattern]]:
    compiled = [
        (category, keyword, re.compile(rf"\b{re.escape(normalize_text(keyword))}\b"))
        for category, keywords in rules.items()
        for keyword in keywords
    ]
    compiled.sort(key=lambda rule: -len(rule[1]))  # "tesco mobile" before "tesco"
    return compiled


_MERCHANT_PATTERNS = _compile(MERCHANT_RULES)
_ITEM_PATTERNS = _compile(ITEM_RULES)


def match_rules(text: str | None, patterns=_MERCHANT_PATTERNS) -> tuple[str, str] | None:
    """(category_name, keyword) for the first (longest) keyword found in `text`."""
    normalised = normalize_text(text)
    if not normalised:
        return None
    for category, keyword, pattern in patterns:
        if pattern.search(normalised):
            return category, keyword
    return None


# -- categories table -----------------------------------------------------------------
def load_categories(db: Session) -> dict[str, Category]:
    """category_name (lower-case) -> Category row, from the live database."""
    return {c.category_name.lower(): c for c in db.scalars(select(Category))}


def _result(categories: dict[str, Category], name: str, confidence: float, source: str, reason: str) -> CategoryResult:
    row = categories.get(name.lower())
    if row is None:
        # The predicted name is not in this database: never invent an id.
        return _default(categories, f"predicted '{name}' but it is not in the categories table")
    return CategoryResult(row.category_id, row.category_name, round(confidence, 3), source, reason)


def _default(categories: dict[str, Category], reason: str) -> CategoryResult:
    row = categories.get(DEFAULT_CATEGORY.lower())
    return CategoryResult(row.category_id if row else None, row.category_name if row else None, 0.0, "default", reason)


# -- ML model -------------------------------------------------------------------------
class CategoryModel:
    """Character n-gram TF-IDF + logistic regression.

    Character n-grams (2-5, word-bounded) cope with OCR noise and store suffixes
    ("TESCO EXPRESS 3021" ~ "Tesco") and give calibrated probabilities, so low
    confidence predictions can be passed to the next tier instead of guessed.
    """

    def __init__(self):
        self._pipeline = None
        self._lock = threading.Lock()
        self.samples = 0
        self.classes: list[str] = []
        self.trained_on: str | None = None

    @property
    def trained(self) -> bool:
        return self._pipeline is not None

    @staticmethod
    def build_pipeline():
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline

        return make_pipeline(
            TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True),
            LogisticRegression(max_iter=2000, class_weight="balanced", C=5.0),
        )

    def train(self, texts: list[str], labels: list[str], source: str = "custom") -> dict:
        pairs = [(model_text(t), l) for t, l in zip(texts, labels) if model_text(t) and l]
        distinct = sorted({label for _, label in pairs})
        if len(pairs) < ML_MIN_SAMPLES or len(distinct) < 2:
            return {"trained": False, "samples": len(pairs),
                    "reason": f"need at least {ML_MIN_SAMPLES} labelled examples in 2+ categories"}
        pipeline = self.build_pipeline()
        pipeline.fit([t for t, _ in pairs], [l for _, l in pairs])
        with self._lock:
            self._pipeline, self.samples, self.classes, self.trained_on = pipeline, len(pairs), distinct, source
        return {"trained": True, "samples": len(pairs), "classes": distinct, "source": source,
                "model_version": MODEL_VERSION}

    def predict(self, text: str | None) -> tuple[str, float] | None:
        with self._lock:
            pipeline = self._pipeline
        text = model_text(text)
        if pipeline is None or not text:
            return None
        probabilities = pipeline.predict_proba([text])[0]
        best = probabilities.argmax()
        return str(pipeline.classes_[best]), float(probabilities[best])


def load_seed_training_data(seed_dir: Path = SEED_DIR, include_items: bool = True) -> tuple[list[str], list[str]]:
    """Labelled examples from the team's seed CSVs (database/*.csv).

    Labels are category *names* (via categories.csv) so they can be mapped onto
    whatever category_ids the live database uses.
    """
    names = {row["category_id"]: row["category_name"] for row in _read_csv(seed_dir / "categories.csv")}
    texts, labels, by_txn = [], [], {}
    for row in _read_csv(seed_dir / "transactions.csv"):
        category = names.get(_int_str(row.get("category_id")))
        if category and row.get("merchant_name"):
            texts.append(row["merchant_name"])
            labels.append(category)
            by_txn[row["transaction_id"]] = category
    if include_items:
        for row in _read_csv(seed_dir / "receipt_items.csv"):
            category = by_txn.get(row.get("transaction_id"))
            if category and row.get("normalized_name"):
                texts.append(row["normalized_name"])
                labels.append(category)
    return texts, labels


def load_database_training_data(db: Session) -> tuple[list[str], list[str]]:
    """Merchant -> category labels already stored in the transactions table."""
    rows = db.execute(
        select(Transaction.merchant_name, Category.category_name)
        .join(Category, Transaction.category_id == Category.category_id)
    ).all()
    return [m for m, _ in rows], [c for _, c in rows]


def _read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _int_str(value) -> str | None:
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return None


category_model = CategoryModel()
_train_lock = threading.Lock()


def get_category_model() -> CategoryModel:
    """Lazily train the shared model on the seed dataset the first time it is needed."""
    if not category_model.trained:
        with _train_lock:
            if not category_model.trained:
                texts, labels = load_seed_training_data()
                info = category_model.train(texts, labels, source="seed_csv")
                logger.info("Category model: %s", {k: v for k, v in info.items() if k != "classes"})
    return category_model


def retrain_from_database(db: Session) -> dict:
    """Retrain on seed data + labels stored in the database (future improvement hook)."""
    texts, labels = load_seed_training_data()
    db_texts, db_labels = load_database_training_data(db)
    return category_model.train(texts + db_texts, labels + db_labels, source="seed_csv+database")


# -- tier 1: the user's own history ---------------------------------------------------
def categorize_from_history(db: Session, user_id: int, merchant: str | None,
                            categories: dict[str, Category]) -> CategoryResult | None:
    key = normalize_text(merchant)
    if key in UNKNOWN_MERCHANTS:
        return None
    rows = db.execute(
        select(Transaction.merchant_name, Transaction.category_id, func.count())
        .where(Transaction.user_id == user_id, Transaction.category_id.is_not(None))
        .group_by(Transaction.merchant_name, Transaction.category_id)
    ).all()
    votes: Counter = Counter()
    for name, category_id, count in rows:
        if normalize_text(name) == key:
            votes[category_id] += count
    if not votes:
        return None
    category_id, count = votes.most_common(1)[0]
    row = next((c for c in categories.values() if c.category_id == category_id), None)
    if row is None:
        return None
    share = count / sum(votes.values())
    return CategoryResult(row.category_id, row.category_name, round(HISTORY_CONFIDENCE * share, 3), "history",
                          f"you categorised {count} earlier transaction(s) from this merchant this way")


# -- tier 4: LM Studio ----------------------------------------------------------------
def categorize_with_llm(client: LMStudioClient, merchant: str | None, description: str | None,
                        categories: dict[str, Category]) -> CategoryResult | None:
    names = [c.category_name for c in categories.values()]
    if not names or not (merchant or description):
        return None
    schema = {
        "type": "object",
        "properties": {"category": {"type": "string", "enum": names}},
        "required": ["category"],
        "additionalProperties": False,
    }
    messages = [
        {"role": "system", "content": (
            "You categorise a student's spending transactions in Ireland. "
            f"Choose exactly one category from: {', '.join(names)}. "
            'Reply only with JSON like {"category": "Groceries"}. If unsure, use Other.'
        )},
        {"role": "user", "content": f"Merchant: {merchant or 'unknown'}\nDescription: {description or 'none'}"},
    ]
    try:
        data = client.chat_json(messages, schema, name="transaction_category", max_tokens=60)
    except LMStudioError as exc:
        logger.info("LLM categorisation unavailable: %s", exc.reason)
        return None
    name = str(data.get("category", "")).strip().lower()
    if name not in categories:  # reject anything off the list
        return None
    return _result(categories, name, LLM_CONFIDENCE, "llm", "suggested by the local LLM (LM Studio)")


# -- public entry points --------------------------------------------------------------
def categorize_transaction(
    db: Session,
    merchant: str | None,
    description: str | None = None,
    *,
    user_id: int | None = None,
    client: LMStudioClient | None = None,
    use_llm: bool = False,
) -> CategoryResult:
    categories = load_categories(db)
    merchant = None if is_unknown_merchant(merchant) else merchant
    description = (description or "").strip() or None
    if not (merchant or description):
        return _default(categories, "no merchant name or description to categorise")

    if user_id is not None and merchant:
        result = categorize_from_history(db, user_id, merchant, categories)
        if result:
            return result

    for label, value in (("merchant", merchant), ("description", description)):
        hit = match_rules(value)
        if hit:
            return _result(categories, hit[0], RULE_CONFIDENCE, "rule", f"{label} matches '{hit[1]}'")

    prediction = get_category_model().predict(" ".join(filter(None, [merchant, description])))
    if prediction and prediction[1] >= ML_MIN_PROBABILITY:
        return _result(categories, prediction[0], prediction[1], "ml",
                       f"predicted by the ML model ({MODEL_VERSION})")

    if use_llm and client is not None:
        result = categorize_with_llm(client, merchant, description, categories)
        if result:
            return result

    detail = f" (best ML guess {prediction[0]} at {prediction[1]:.0%})" if prediction else ""
    return _default(categories, "unknown merchant: no rule, history or confident model match" + detail)


def categorize_receipt(
    db: Session,
    merchant: str | None,
    items: list[dict],
    *,
    user_id: int | None = None,
) -> CategoryResult:
    """Category for an OCR'd receipt: the merchant if recognisable, else its items.

    Items vote with their line totals (quantity x unit_price), so the category
    carrying most of the money wins.
    """
    result = categorize_transaction(db, merchant, None, user_id=user_id)
    if result.source != "default" or not items:
        return result

    categories = load_categories(db)
    model = get_category_model()
    totals: dict[str, float] = defaultdict(float)
    for item in items:
        name = item.get("item_name") or item.get("normalized_name")
        hit = match_rules(name, _ITEM_PATTERNS)
        category = hit[0] if hit else None
        if category is None:
            prediction = model.predict(name)
            if prediction and prediction[1] >= ML_MIN_PROBABILITY:
                category = prediction[0]
        if category:
            totals[category] += _line_total(item)
    if not totals:
        return result
    best = max(totals, key=totals.get)
    share = totals[best] / (sum(totals.values()) or 1)
    return _result(categories, best, 0.8 * share, "rule",
                   f"merchant unknown; {share:.0%} of the recognised items are {best}")


def _line_total(item: dict) -> float:
    try:
        return float(item.get("quantity") or 1) * float(item.get("unit_price") or 0) or 0.01
    except (TypeError, ValueError):
        return 0.01

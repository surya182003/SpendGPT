// All the calls to the FastAPI backend are in this file.

const API_URL = "http://localhost:8000";

// Sends the request and returns the JSON the backend answers with
// If something goes wrong it throws an Error with a message we can show on screen
async function request(path, options) {
  let response;
  try {
    response = await fetch(API_URL + path, options);
  } catch {
    // also happens when the backend crashes on a request (check the backend terminal)
    throw new Error("Could not reach the server. Is the backend running?");
  }

  const data = await response.json();

  if (!response.ok) {
    // the backend sends errors as { detail: "text" } or { detail: { message, validation_issues } }
    let message = "Something went wrong";
    if (typeof data.detail === "string") {
      message = data.detail;
      } else if (Array.isArray(data.detail) && data.detail.length > 0) {
      // a form that was filled in wrongly, like a bad email address
      message = data.detail[0].msg;
    } else if (data.detail && data.detail.message) {
      message = data.detail.message;
      if (data.detail.validation_issues && data.detail.validation_issues.length > 0) {
        message = message + " (" + data.detail.validation_issues.join(", ") + ")";
      }
    }
    throw new Error(message);
  }

  return data;
}

// Logs in and gives back the user: { user_id, first_name, last_name, email }
// This is how we get the user id from the email
export async function loginUser(email, password) {
  const data = await request("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: email, password: password }),
  });
  return data.user;
}

// Makes a new account and gives back the new user: { user_id, first_name, last_name, email }
export async function registerUser(firstName, lastName, email, password) {
  const data = await request("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ first_name: firstName, last_name: lastName, email: email, password: password }),
  });
  return data.user;
}
// Sends the receipt picture to the backend to be read (OCR) and saved
export async function uploadReceipt(userId, file) {
  const formData = new FormData();
  formData.append("user_id", userId);
  formData.append("file", file);

  return request("/api/receipts/upload", { method: "POST", body: formData });
}

// All the receipts saved for one user
export async function getUserReceipts(userId) {
  return request("/api/ai/users/" + userId + "/receipts");
}
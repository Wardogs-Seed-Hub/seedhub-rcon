"use strict";
document.querySelectorAll("[data-copy]").forEach(button => button.addEventListener("click", async () => {
  const input = document.getElementById(button.dataset.copy);
  const status = document.getElementById("copy-status");
  try { await navigator.clipboard.writeText(input.value); status.textContent = "Copied."; }
  catch { input.select(); status.textContent = "Select and copy the key manually."; }
}));
document.querySelectorAll("form").forEach(form => form.addEventListener("submit", () => {
  const button = form.querySelector("[data-busy]");
  if (button) { button.disabled = true; button.textContent = button.dataset.busy; }
}));

// Attach handlers for normal upload and debug upload
document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("uploadForm");
  const fileInput = document.getElementById("fileInput");
  const productEl = document.getElementById("product");
  const versionEl = document.getElementById("version");
  const appIdEl = document.getElementById("app_id");
  const spinner = document.getElementById("spinner");
  const result = document.getElementById("result");
  const downloadLink = document.getElementById("downloadLink");
  const debugButton = document.getElementById("debugButton");
  const debugResponse = document.getElementById("debugResponse");

  function showSpinner() {
    spinner.style.display = "block";
  }
  function hideSpinner() {
    spinner.style.display = "none";
  }

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    debugResponse.textContent = "";
    result.style.display = "none";

    const product = productEl.value;
    const version = versionEl.value;
    const app_id = appIdEl.value;

    if (!fileInput.files.length) {
      alert("Please select a file to upload.");
      return;
    }

    if (!app_id || !/^\d+$/.test(app_id)) {
      alert("Please choose a numeric App ID.");
      return;
    }

    const fd = new FormData();
    fd.append("product", product);
    fd.append("version", version);
    fd.append("app_id", app_id); // EXACT name used by backend
    fd.append("file", fileInput.files[0]);

    showSpinner();
    try {
      const resp = await fetch("/upload-file/", { method: "POST", body: fd });
      if (resp.ok) {
        const blob = await resp.blob();
        const url = window.URL.createObjectURL(blob);
        downloadLink.href = url;
        const fname = fileInput.files[0].name.replace(/\.[^/.]+$/, "") + "_processed" + (fileInput.files[0].name.match(/\.[^/.]+$/) || "");
        downloadLink.download = fname;
        result.style.display = "block";
      } else {
        let msg = `Error: ${resp.status}`;
        try {
          const j = await resp.json();
          if (j && j.error) msg = `Error: ${j.error}`;
          else if (j && j.detail) msg = `Error: ${JSON.stringify(j.detail)}`;
        } catch (e) {
          // ignore JSON parse error
        }
        alert(msg);
      }
    } catch (err) {
      console.error(err);
      alert("Network or unexpected error while uploading.");
    } finally {
      hideSpinner();
    }
  });

  // Debug button: send form to /debug-form/ to see what server received
  debugButton.addEventListener("click", async function () {
    debugResponse.textContent = "";
    const product = productEl.value;
    const version = versionEl.value;
    const app_id = appIdEl.value;

    if (!fileInput.files.length) {
      alert("Please select a file to upload for debug.");
      return;
    }

    const fd = new FormData();
    fd.append("product", product);
    fd.append("version", version);
    fd.append("app_id", app_id);
    fd.append("file", fileInput.files[0]);

    showSpinner();
    try {
      const resp = await fetch("/debug-form/", { method: "POST", body: fd });
      const j = await resp.json();
      debugResponse.textContent = JSON.stringify(j, null, 2);
    } catch (err) {
      console.error(err);
      debugResponse.textContent = "Error contacting debug endpoint.";
    } finally {
      hideSpinner();
    }
  });
});
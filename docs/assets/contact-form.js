// Contact form: posts to Web3Forms (https://web3forms.com), which emails the submission.
(function () {
  var ENDPOINT = "https://api.web3forms.com/submit";

  document.querySelectorAll("form.q-contact-form").forEach(function (form) {
    var status = form.querySelector(".q-form-status");
    var button = form.querySelector("button[type=submit]");

    function show(msg, ok) {
      status.textContent = msg;
      status.className = "q-form-status " + (ok ? "is-success" : "is-error");
    }

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (!form.reportValidity()) return;

      var data = Object.fromEntries(new FormData(form));
      if (!data.access_key || data.access_key.indexOf("YOUR_") === 0) {
        console.warn("contact-form: Web3Forms access key is not configured");
        show("Formuläret är inte konfigurerat ännu. Mejla oss istället.", false);
        return;
      }

      button.disabled = true;
      button.textContent = "Skickar…";
      status.className = "q-form-status";

      fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(data),
      })
        .then(function (r) { return r.json(); })
        .then(function (res) {
          if (!res.success) throw new Error(res.message);
          form.reset();
          show("Tack! Vi har tagit emot ditt meddelande och återkommer så snart vi kan.", true);
          (window.dataLayer = window.dataLayer || []).push({ event: "contact_form_submit" });
        })
        .catch(function (err) {
          console.error("contact-form:", err);
          show("Något gick fel och meddelandet skickades inte. Försök igen om en stund.", false);
        })
        .finally(function () {
          button.disabled = false;
          button.textContent = "Skicka";
        });
    });
  });
})();

(() => {
  // src/js/language.js
  document.addEventListener("DOMContentLoaded", function() {
    const langToggle = document.getElementById("lang-toggle");
    const langDropdown = document.getElementById("lang-dropdown");
    const langForm = document.getElementById("language-form");
    const langInput = document.getElementById("language-input");
    const langOptions = document.querySelectorAll(".lang-option");
    if (!langToggle || !langDropdown) return;
    langToggle.addEventListener("click", function(e) {
      e.stopPropagation();
      langDropdown.classList.toggle("hidden");
    });
    document.addEventListener("click", function(e) {
      if (!langDropdown.contains(e.target) && !langToggle.contains(e.target)) {
        langDropdown.classList.add("hidden");
      }
    });
    langOptions.forEach(function(option) {
      option.addEventListener("click", function() {
        const lang = this.getAttribute("data-lang");
        langInput.value = lang;
        langForm.submit();
      });
    });
    document.addEventListener("keydown", function(e) {
      if (e.key === "Escape") {
        langDropdown.classList.add("hidden");
      }
    });
  });
})();

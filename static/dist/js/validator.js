(() => {
  // src/js/validator.js
  var FormValidator = class {
    constructor(form) {
      this.form = form;
      this.messages = {
        required: form.dataset.msgRequired || "Required",
        minLength: form.dataset.msgMinLength || "Too short",
        passwordMatch: form.dataset.msgPasswordMatch || "Does not match",
        passwordWeak: form.dataset.msgPasswordWeak || "Too weak",
        email: form.dataset.msgEmail || "Invalid email",
        phone: form.dataset.msgPhone || "Invalid phone",
        noDigits: form.dataset.msgNoDigits || "Numbers not allowed"
      };
    }
    validate() {
      let isValid = true;
      this.form.querySelectorAll("[data-validate]").forEach((input) => {
        const error = this.validateInput(input);
        if (error) {
          this.showError(input, error);
          isValid = false;
        } else {
          this.clearError(input);
        }
      });
      return isValid;
    }
    validateInput(input) {
      const value = input.value.trim();
      const rules = input.dataset.validate.split("|");
      for (const rule of rules) {
        const [name, param] = rule.split(":");
        if (name === "required" && !value) {
          return this.messages.required;
        }
        if (name === "min" && value.length < parseInt(param)) {
          return this.messages.minLength;
        }
        if (name === "password" && (!/\d/.test(value) || !/[!@#$%^&*(),.?":{}|<>_\-]/.test(value))) {
          return this.messages.passwordWeak;
        }
        if (name === "match") {
          const target = document.getElementById(param);
          if (target && value !== target.value) {
            return this.messages.passwordMatch;
          }
        }
        if (name === "email" && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
          return this.messages.email;
        }
        if (name === "phone" && !/^\+\d{7,15}$/.test(value.replace(/\s/g, ""))) {
          return this.messages.phone;
        }
        if (name === "nodigits" && /\d/.test(value)) {
          return this.messages.noDigits;
        }
      }
      return null;
    }
    showError(input, message) {
      const wrapper = input.closest(".flex.flex-col.gap-2");
      const errorEl = wrapper?.querySelector(".input-error");
      input.closest(".input-floating")?.classList.add("error");
      if (errorEl) {
        errorEl.textContent = message;
        errorEl.classList.remove("hidden");
      }
    }
    clearError(input) {
      const wrapper = input.closest(".flex.flex-col.gap-2");
      const errorEl = wrapper?.querySelector(".input-error");
      input.closest(".input-floating")?.classList.remove("error");
      if (errorEl) {
        errorEl.textContent = "";
        errorEl.classList.add("hidden");
      }
    }
  };
  var ResendCooldown = {
    COOLDOWN_MS: 3 * 60 * 1e3,
    // 3 минуты
    getKey(email) {
      return `resend_cooldown_${email}`;
    },
    setCooldown(email) {
      const expiry = Date.now() + this.COOLDOWN_MS;
      localStorage.setItem(this.getKey(email), expiry.toString());
    },
    getRemainingTime(email) {
      const expiry = localStorage.getItem(this.getKey(email));
      if (!expiry) return 0;
      const remaining = parseInt(expiry) - Date.now();
      return remaining > 0 ? remaining : 0;
    },
    isOnCooldown(email) {
      return this.getRemainingTime(email) > 0;
    },
    formatTime(ms) {
      const minutes = Math.floor(ms / 6e4);
      const seconds = Math.floor(ms % 6e4 / 1e3);
      return `${minutes}:${seconds.toString().padStart(2, "0")}`;
    }
  };
  var resendTimerInterval = null;
  function startResendTimer(email) {
    const btn = document.getElementById("resend-email");
    if (!btn) return;
    if (resendTimerInterval) {
      clearInterval(resendTimerInterval);
    }
    function updateButton() {
      const remaining = ResendCooldown.getRemainingTime(email);
      if (remaining > 0) {
        btn.disabled = true;
        btn.textContent = `Resend in ${ResendCooldown.formatTime(remaining)}`;
      } else {
        btn.disabled = false;
        btn.textContent = "Didn't receive? Resend";
        clearInterval(resendTimerInterval);
      }
    }
    updateButton();
    resendTimerInterval = setInterval(updateButton, 1e3);
  }
  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("form[data-msg-required]").forEach((form) => {
      const validator = new FormValidator(form);
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (!validator.validate()) return;
        if (form.id === "forgot-password-form") {
          const emailInput = form.querySelector('input[type="email"]');
          const email = emailInput.value.trim();
          const submitBtn = form.querySelector('button[type="submit"]');
          const btnText = submitBtn.querySelector(".btn-text");
          const btnLoader = submitBtn.querySelector(".btn-loader");
          const errorDiv = form.querySelector(".input-error");
          if (btnText) btnText.classList.add("hidden");
          if (btnLoader) btnLoader.classList.remove("hidden");
          submitBtn.disabled = true;
          try {
            const response = await fetch(form.dataset.action, {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": form.querySelector('[name="csrfmiddlewaretoken"]')?.value || getCookie("csrftoken")
              },
              body: JSON.stringify({ email })
            });
            const data = await response.json();
            if (data.success) {
              ResendCooldown.setCooldown(email);
              document.getElementById("sent-email").textContent = email;
              document.getElementById("modal-forgot-password")?.classList.remove("active");
              document.getElementById("modal-check-email")?.classList.add("active");
              startResendTimer(email);
              form.reset();
            } else {
              if (errorDiv) {
                errorDiv.textContent = data.error || "Something went wrong";
                errorDiv.classList.remove("hidden");
              }
            }
          } catch (error) {
            console.error("Error:", error);
            if (errorDiv) {
              errorDiv.textContent = "Network error. Please try again.";
              errorDiv.classList.remove("hidden");
            }
          } finally {
            if (btnText) btnText.classList.remove("hidden");
            if (btnLoader) btnLoader.classList.add("hidden");
            submitBtn.disabled = false;
          }
          return;
        }
        form.submit();
      });
      form.querySelectorAll("[data-validate]").forEach((input) => {
        input.addEventListener("blur", () => {
          const error = validator.validateInput(input);
          error ? validator.showError(input, error) : validator.clearError(input);
        });
        input.addEventListener("input", () => validator.clearError(input));
      });
    });
    document.getElementById("resend-email")?.addEventListener("click", async (e) => {
      const btn = e.target;
      const email = document.getElementById("sent-email")?.textContent;
      if (!email || ResendCooldown.isOnCooldown(email)) return;
      btn.disabled = true;
      btn.textContent = "Sending...";
      try {
        await new Promise((resolve) => setTimeout(resolve, 1e3));
        ResendCooldown.setCooldown(email);
        btn.textContent = "Email sent!";
        setTimeout(() => startResendTimer(email), 1500);
      } catch (error) {
        btn.textContent = "Error. Try again";
        btn.disabled = false;
      }
    });
    const checkEmailModal = document.getElementById("modal-check-email");
    if (checkEmailModal) {
      const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
          if (mutation.target.classList.contains("active")) {
            const email = document.getElementById("sent-email")?.textContent;
            if (email) startResendTimer(email);
          }
        });
      });
      observer.observe(checkEmailModal, { attributes: true, attributeFilter: ["class"] });
    }
  });
})();

(() => {
  // src/js/qr.js
  var QRManager = {
    timerInterval: null,
    guestLink: null,
    currentBookingId: null,
    // Генерация QR
    generate(canvasId, data) {
      const canvas = document.getElementById(canvasId);
      if (!canvas) {
        console.error("Canvas not found:", canvasId);
        return;
      }
      new QRious({
        element: canvas,
        value: data,
        size: 200,
        background: "#FDEFD3",
        foreground: "#000000",
        level: "M"
      });
    },
    // Запуск таймера (минуты)
    startTimer(minutes, onExpire) {
      this.stopTimer();
      let seconds = Math.round(minutes * 60);
      const timerEl = document.getElementById("qr-minutes");
      const updateDisplay = () => {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        if (timerEl) {
          timerEl.textContent = secs > 0 ? `${mins}:${secs.toString().padStart(2, "0")}` : mins;
        }
        if (seconds <= 0) {
          this.stopTimer();
          if (onExpire) onExpire();
        }
        seconds--;
      };
      updateDisplay();
      this.timerInterval = setInterval(updateDisplay, 1e3);
    },
    stopTimer() {
      if (this.timerInterval) {
        clearInterval(this.timerInterval);
        this.timerInterval = null;
      }
    },
    // Получить CSRF токен
    getCsrfToken() {
      return document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
    },
    // Запросить токен с бэкенда и показать QR
    async showUnitQR(bookingId) {
      this.currentBookingId = bookingId;
      try {
        const response = await fetch("/visit/generate/", {
          method: "POST",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-CSRFToken": this.getCsrfToken(),
            "X-Requested-With": "XMLHttpRequest"
          },
          body: `booking_id=${bookingId}`
        });
        const data = await response.json();
        if (data.success) {
          document.getElementById("qr-unit-number").textContent = data.full_code;
          document.getElementById("modal-qr-code")?.classList.add("active");
          document.body.style.overflow = "hidden";
          setTimeout(() => {
            this.generate("qr-canvas", data.token);
            this.startTimer(data.expires_in, () => {
              alert("QR code expired. Please generate a new one.");
              document.getElementById("modal-qr-code")?.classList.remove("active");
              document.body.style.overflow = "";
            });
          }, 100);
        } else {
          alert(data.error || "Failed to generate QR code");
        }
      } catch (error) {
        console.error("Error generating QR:", error);
        alert("Failed to generate QR code");
      }
    },
    // Запросить гостевой токен (без имени — его введёт менеджер)
    async showGuestQR() {
      if (!this.currentBookingId) {
        alert("No booking selected");
        return;
      }
      try {
        const response = await fetch("/visit/generate-guest/", {
          method: "POST",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-CSRFToken": this.getCsrfToken(),
            "X-Requested-With": "XMLHttpRequest"
          },
          body: `booking_id=${this.currentBookingId}`
        });
        const data = await response.json();
        if (data.success) {
          this.guestLink = data.guest_link;
          document.getElementById("guest-unit-number").textContent = data.full_code;
          const guestTimerEl = document.getElementById("guest-expires-in");
          if (guestTimerEl) {
            guestTimerEl.textContent = data.expires_in;
          }
          document.getElementById("modal-qr-code")?.classList.remove("active");
          document.getElementById("modal-guest-qr")?.classList.add("active");
          setTimeout(() => {
            this.generate("guest-qr-canvas", data.token);
          }, 100);
        } else {
          alert(data.error || "Failed to generate guest QR");
        }
      } catch (error) {
        console.error("Error generating guest QR:", error);
        alert("Failed to generate guest QR");
      }
    }
  };
  document.addEventListener("DOMContentLoaded", () => {
    document.addEventListener("click", (e) => {
      const btn = e.target.closest(".btn-show-qr");
      if (!btn) return;
      const bookingId = btn.dataset.booking;
      if (bookingId) {
        QRManager.showUnitQR(bookingId);
      }
    });
    document.getElementById("btn-share-guest")?.addEventListener("click", () => {
      QRManager.showGuestQR();
    });
    document.getElementById("btn-copy-guest-link")?.addEventListener("click", async () => {
      const btn = document.getElementById("btn-copy-guest-link");
      try {
        await navigator.clipboard.writeText(QRManager.guestLink);
        btn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
                Copied!
            `;
        setTimeout(() => {
          btn.innerHTML = `
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path>
                        <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path>
                    </svg>
                    Copy link
                `;
        }, 2e3);
      } catch (error) {
        alert("Failed to copy link");
      }
    });
    document.querySelectorAll("#modal-qr-code .modal-close").forEach((btn) => {
      btn.addEventListener("click", () => QRManager.stopTimer());
    });
  });
})();

// Helper: получить CSRF токен из cookie
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// открытие модельного окна
document.addEventListener('DOMContentLoaded', () => {
    const menu = document.getElementById('menu');
    const overlay = document.getElementById('menu-overlay');
    const toggleBtn = document.getElementById('menu-toggle');
    const closeBtn = document.getElementById('menu-close');


    const openMenu = () => {
        menu.classList.remove('-translate-x-full');
        overlay.classList.remove('hidden');
        document.body.classList.add('overflow-hidden');
    };

    const closeMenu = () => {
        menu.classList.add('-translate-x-full');
        overlay.classList.add('hidden');
        document.body.classList.remove('overflow-hidden');
    };

    toggleBtn?.addEventListener('click', openMenu);
    closeBtn?.addEventListener('click', closeMenu);
    overlay?.addEventListener('click', closeMenu);
});

// Language dropdown
document.addEventListener('DOMContentLoaded', () => {
    const langToggle = document.getElementById('lang-toggle');
    const langDropdown = document.getElementById('lang-dropdown');
    const langArrow = document.getElementById('lang-arrow');
    const langForm = document.getElementById('language-form');
    const langInput = document.getElementById('language-input');
    const langNext = document.getElementById('language-next');
    const langOptions = document.querySelectorAll('.lang-option');

    if (!langToggle || !langDropdown) return;

    // Вычисляем путь без языкового префикса
    const getPathWithoutLang = () => {
        const path = window.location.pathname;
        // Убираем /ru/, /ar/, /en/ из начала пути
        return path.replace(/^\/(ru|ar|en)(\/|$)/, '/') || '/';
    };

    // Устанавливаем правильный next при загрузке
    if (langNext) {
        langNext.value = getPathWithoutLang();
    }

    // Toggle dropdown
    langToggle.addEventListener('click', (e) => {
        e.stopPropagation();
        langDropdown.classList.toggle('hidden');
        langArrow?.classList.toggle('rotate-180');
    });

    // Select language
    langOptions.forEach(option => {
        option.addEventListener('click', () => {
            const lang = option.dataset.lang;

            if (langForm && langInput) {
                langInput.value = lang;
                // Обновляем next перед отправкой
                if (langNext) {
                    langNext.value = getPathWithoutLang();
                }
                langForm.submit();
            }
        });
    });

    // Close on outside click
    document.addEventListener('click', (e) => {
        if (!langDropdown.contains(e.target) && !langToggle.contains(e.target)) {
            langDropdown.classList.add('hidden');
            langArrow?.classList.remove('rotate-180');
        }
    });

    // Close on Escape
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            langDropdown.classList.add('hidden');
            langArrow?.classList.remove('rotate-180');
        }
    });
});

//Увеличение лого на hero
document.addEventListener('DOMContentLoaded', () => {
    const logo = document.getElementById('hero-logo');
    const hero = document.getElementById('hero');

    if (!logo || !hero) return;

    const updateLogoScale = () => {
        const heroRect = hero.getBoundingClientRect();
        const heroHeight = hero.offsetHeight;
        const scrolled = -heroRect.top;

        // Прогресс от 0 до 1, но в 2 раза быстрее
        const progress = Math.min(Math.max((scrolled / heroHeight) * 2, 0), 1);

        // Scale от 0.7 до 1
        const scale = 0.7 + (progress * 0.3);

        logo.style.transform = `scale(${scale})`;
    };

    window.addEventListener('scroll', updateLogoScale);
    updateLogoScale();
});


// анимация при наведении блока приемуществ на главной
document.addEventListener('DOMContentLoaded', () => {
    const benefitsSection = document.getElementById('benefits');
    const reserveBtn = benefitsSection?.querySelector('.btn-default.primary');

    if (!benefitsSection || !reserveBtn) return;

    reserveBtn.addEventListener('mouseenter', () => {
        benefitsSection.classList.add('active');
    });

    reserveBtn.addEventListener('mouseleave', () => {
        benefitsSection.classList.remove('active');
    });
});


// slider на главной take a look inside
document.addEventListener('DOMContentLoaded', () => {
    const slider = document.querySelector('.gallery-slider');
    if (!slider) return;

    const slides = slider.querySelectorAll('.gallery-slide');
    const titles = slider.querySelectorAll('.gallery-title');
    const dotsContainer = slider.querySelector('.gallery-dots');
    const prevBtn = slider.querySelector('.gallery-control.prev');
    const nextBtn = slider.querySelector('.gallery-control.next');

    if (!slides.length) return;

    let currentIndex = 0;
    const totalSlides = slides.length;
    let autoPlayInterval;

    // Инициализация: добавляем индексы и генерируем dots
    const init = () => {
        slides.forEach((slide, i) => {
            slide.dataset.index = i;
            if (i === 0) slide.classList.add('active');
        });

        titles.forEach((title, i) => {
            title.dataset.index = i;
            if (i === 0) title.classList.add('active');
        });

        // Генерируем dots
        if (dotsContainer) {
            dotsContainer.innerHTML = '';
            for (let i = 0; i < totalSlides; i++) {
                const dot = document.createElement('button');
                dot.className = `gallery-dot${i === 0 ? ' active' : ''}`;
                dot.dataset.index = i;
                dot.setAttribute('aria-label', `Go to slide ${i + 1}`);
                dot.addEventListener('click', () => {
                    goToSlide(i);
                    resetAutoPlay();
                });
                dotsContainer.appendChild(dot);
            }
        }
    };

    const goToSlide = (index) => {
        if (index < 0) index = totalSlides - 1;
        if (index >= totalSlides) index = 0;

        slides.forEach(slide => slide.classList.remove('active'));
        slides[index].classList.add('active');

        titles.forEach(title => title.classList.remove('active'));
        if (titles[index]) titles[index].classList.add('active');

        const dots = slider.querySelectorAll('.gallery-dot');
        dots.forEach(dot => dot.classList.remove('active'));
        if (dots[index]) dots[index].classList.add('active');

        currentIndex = index;
    };

    const nextSlide = () => goToSlide(currentIndex + 1);
    const prevSlide = () => goToSlide(currentIndex - 1);

    // Controls
    prevBtn?.addEventListener('click', () => {
        prevSlide();
        resetAutoPlay();
    });

    nextBtn?.addEventListener('click', () => {
        nextSlide();
        resetAutoPlay();
    });

    // Auto-play
    const startAutoPlay = () => {
        autoPlayInterval = setInterval(nextSlide, 5000);
    };

    const resetAutoPlay = () => {
        clearInterval(autoPlayInterval);
        startAutoPlay();
    };

    // Touch/Swipe
    let touchStartX = 0;

    slider.addEventListener('touchstart', (e) => {
        touchStartX = e.changedTouches[0].screenX;
    }, { passive: true });

    slider.addEventListener('touchend', (e) => {
        const diff = touchStartX - e.changedTouches[0].screenX;
        if (Math.abs(diff) > 50) {
            diff > 0 ? nextSlide() : prevSlide();
            resetAutoPlay();
        }
    }, { passive: true });

    // Keyboard
    slider.setAttribute('tabindex', '0');
    slider.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowLeft') {
            prevSlide();
            resetAutoPlay();
        } else if (e.key === 'ArrowRight') {
            nextSlide();
            resetAutoPlay();
        }
    });

    // Start
    init();
    startAutoPlay();
});


//calculator
document.addEventListener('DOMContentLoaded', () => {
    const periodInputs = document.querySelectorAll('input[name="period"]');
    const addonInputs = document.querySelectorAll('input[name="addons"]');
    const totalPriceEl = document.getElementById('total-price');
    const originalPriceEl = document.getElementById('original-price');

    if (!totalPriceEl) return;

    const formatPrice = (price) => {
        return `AED ${price.toLocaleString()}`;
    };

    const calculateTotal = () => {
        let total = 0;
        let original = 0;
        let hasDiscount = false;

        // Период
        const selectedPeriod = document.querySelector('input[name="period"]:checked');
        if (selectedPeriod) {
            total += parseInt(selectedPeriod.dataset.price) || 0;
            original += parseInt(selectedPeriod.dataset.original) || parseInt(selectedPeriod.dataset.price) || 0;
            if (selectedPeriod.dataset.discount && parseInt(selectedPeriod.dataset.discount) > 0) {
                hasDiscount = true;
            }
        }

        // Дополнительные услуги
        addonInputs.forEach(input => {
            if (input.checked) {
                const addonPrice = parseInt(input.dataset.price) || 0;
                total += addonPrice;
                original += addonPrice;
            }
        });

        // Обновляем UI
        totalPriceEl.textContent = formatPrice(total);

        if (hasDiscount && original > total) {
            originalPriceEl.textContent = `/ ${formatPrice(original)}`;
            originalPriceEl.classList.remove('hidden');
        } else {
            originalPriceEl.classList.add('hidden');
        }
    };

    // Слушаем изменения
    periodInputs.forEach(input => {
        input.addEventListener('change', calculateTotal);
    });

    addonInputs.forEach(input => {
        input.addEventListener('change', calculateTotal);
    });

    // Начальный расчёт
    calculateTotal();
});


// copy btn
document.addEventListener('DOMContentLoaded', () => {
    const copyBtns = document.querySelectorAll('[data-copy-target]');

    copyBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetId = btn.dataset.copyTarget;
            const targetEl = document.getElementById(targetId);
            if (!targetEl) return;

            const text = targetEl.textContent.trim();
            const successText = btn.dataset.copySuccess || 'Copied!';
            const originalText = btn.textContent;

            navigator.clipboard.writeText(text).then(() => {
                btn.textContent = successText;
                setTimeout(() => {
                    btn.textContent = originalText;
                }, 2000);
            });
        });
    });
});


// Leaflet maps
let leafletMaps = {};

function initLeafletMaps() {
    const mapElements = document.querySelectorAll('#map[data-coordinates]');

    mapElements.forEach(mapEl => {
        const coords = mapEl.dataset.coordinates;
        if (!coords || leafletMaps[mapEl.id]) return;

        const [lat, lng] = coords.split(',').map(c => parseFloat(c.trim()));

        const map = L.map(mapEl, {
            zoomControl: false
        }).setView([lat, lng], 15);

        L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', {
            attribution: '© OpenStreetMap'
        }).addTo(map);

        const orangeIcon = L.divIcon({
            html: `<svg width="40" height="48" viewBox="0 0 40 48" fill="#E26137" xmlns="http://www.w3.org/2000/svg">
                <path d="M20 0C9 0 0 9 0 20c0 15 20 28 20 28s20-13 20-28c0-11-9-20-20-20zm0 27c-3.9 0-7-3.1-7-7s3.1-7 7-7 7 3.1 7 7-3.1 7-7 7z"/>
                <circle cx="20" cy="20" r="5" fill="white"/>
            </svg>`,
            className: '',
            iconSize: [40, 48],
            iconAnchor: [20, 48]
        });

        L.marker([lat, lng], { icon: orangeIcon }).addTo(map);

        // Сохраняем ссылку
        leafletMaps[mapEl.id] = map;
    });
}

// Tabs
function initTabs() {
    const tabButtons = document.querySelectorAll('[data-tab]');

    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.dataset.tab;
            const parent = btn.closest('.flex.flex-col');

            if (!parent) return;

            // Убираем active у всех кнопок
            parent.querySelectorAll('[data-tab]').forEach(b => {
                b.classList.remove('active');
            });

            // Добавляем active текущей
            btn.classList.add('active');

            // Скрываем все tab-content
            parent.querySelectorAll('[data-tab-content]').forEach(content => {
                content.classList.add('hidden');
            });

            // Показываем нужный
            const activeContent = parent.querySelector(`[data-tab-content="${tabId}"]`);
            if (activeContent) {
                activeContent.classList.remove('hidden');
            }

            // Если открыли location — обновляем размер карты
            if (tabId === 'location' && leafletMaps['map']) {
                setTimeout(() => {
                    leafletMaps['map'].invalidateSize();
                }, 100);
            }
        });
    });
}

document.addEventListener('DOMContentLoaded', () => {
    if (typeof L !== 'undefined') {
        initLeafletMaps();
    }
    initTabs();
});


// Modals
// Открытие (с закрытием текущей модалки)
document.querySelectorAll('.modal-open').forEach(btn => {
    btn.addEventListener('click', () => {
        const modalId = btn.dataset.modal;

        // Закрыть текущую модалку если кнопка внутри неё
        const currentModal = btn.closest('.modal-overlay');
        if (currentModal) {
            currentModal.classList.remove('active');
        }

        // Открыть новую
        document.getElementById(modalId)?.classList.add('active');
        document.body.style.overflow = 'hidden';
    });
});

// Закрытие по кнопке
document.querySelectorAll('.modal-close').forEach(btn => {
    btn.addEventListener('click', () => {
        btn.closest('.modal-overlay')?.classList.remove('active');
        document.body.style.overflow = '';
    });
});

// Закрытие по клику на оверлей
document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            overlay.classList.remove('active');
            document.body.style.overflow = '';
        }
    });
});

// Закрытие по Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal-overlay.active').forEach(modal => {
            modal.classList.remove('active');
        });
        document.body.style.overflow = '';
    }
});



//phone mask
document.addEventListener('DOMContentLoaded', () => {
    const phoneInput = document.querySelector('#phone');

    if (phoneInput) {
        phoneInput.addEventListener('input', (e) => {
            // Убираем всё кроме цифр
            let value = e.target.value.replace(/\D/g, '');

            // Добавляем + в начало
            e.target.value = value ? '+' + value : '';
        });

        // При фокусе добавляем + если пусто
        phoneInput.addEventListener('focus', (e) => {
            if (!e.target.value) {
                e.target.value = '+';
            }
        });

        // При потере фокуса убираем одинокий +
        phoneInput.addEventListener('blur', (e) => {
            if (e.target.value === '+') {
                e.target.value = '';
            }
        });
    }
});


//show password
document.querySelectorAll('.password-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
        const input = btn.parentElement.querySelector('input');
        const eyeOpen = btn.querySelector('.eye-open');
        const eyeClosed = btn.querySelector('.eye-closed');

        if (input.type === 'password') {
            input.type = 'text';
            eyeOpen.classList.remove('hidden');
            eyeClosed.classList.add('hidden');
        } else {
            input.type = 'password';
            eyeOpen.classList.add('hidden');
            eyeClosed.classList.remove('hidden');
        }
    });
});


// Показ модалки успешного сброса пароля при ?reset=success
document.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('reset') === 'success') {
        document.getElementById('modal-password-reset-success')?.classList.add('active');
        // Убираем параметр из URL
        window.history.replaceState({}, '', window.location.pathname);
    }
});


// ==========================================
// BOOKING FORM HANDLER
// ==========================================

document.addEventListener('DOMContentLoaded', () => {
    const bookingForm = document.querySelector('form[action*="/booking/"]');
    if (!bookingForm) return;

    const isAuth = typeof isAuthenticated !== 'undefined' ? isAuthenticated : false;

    // При загрузке — проверить pending booking
    if (isAuth) {
        const pendingBookingStr = sessionStorage.getItem('pendingBooking');

        if (pendingBookingStr) {
            const data = JSON.parse(pendingBookingStr);

            if (!data.period) {
                sessionStorage.removeItem('pendingBooking');
                return;
            }

            sessionStorage.removeItem('pendingBooking');

            const csrfToken = getCookie('csrftoken');
            if (!csrfToken) {
                alert('Session error. Please try again.');
                return;
            }

            const form = document.createElement('form');
            form.setAttribute('method', 'POST');
            form.setAttribute('action', data.url);
            form.style.display = 'none';

            const csrf = document.createElement('input');
            csrf.setAttribute('type', 'hidden');
            csrf.setAttribute('name', 'csrfmiddlewaretoken');
            csrf.setAttribute('value', csrfToken);
            form.appendChild(csrf);

            const period = document.createElement('input');
            period.setAttribute('type', 'hidden');
            period.setAttribute('name', 'period');
            period.setAttribute('value', data.period);
            form.appendChild(period);

            if (data.addons && data.addons.length > 0) {
                data.addons.forEach(addonId => {
                    const input = document.createElement('input');
                    input.setAttribute('type', 'hidden');
                    input.setAttribute('name', 'addons');
                    input.setAttribute('value', addonId);
                    form.appendChild(input);
                });
            }

            document.body.appendChild(form);
            form.submit();
            return;
        }
    }

    // Submit handler
    bookingForm.addEventListener('submit', function(e) {
        const selectedPeriod = document.querySelector('input[name="period"]:checked');
        if (!selectedPeriod) {
            e.preventDefault();
            alert('Please select a rental period');
            return;
        }

        if (!isAuth) {
            e.preventDefault();

            const periodValue = selectedPeriod.value;
            const addonValues = [];
            document.querySelectorAll('input[name="addons"]:checked').forEach(input => {
                addonValues.push(input.value);
            });

            sessionStorage.setItem('pendingBooking', JSON.stringify({
                url: bookingForm.action,
                period: periodValue,
                addons: addonValues
            }));

            const nextUrl = encodeURIComponent(window.location.pathname);

            const modal = document.getElementById('modal-sign-in');
            if (modal) {
                // Обновить все ссылки с next параметром
                modal.querySelectorAll('.btn-email-login, .btn-google-login, .btn-apple-login, .btn-register-link').forEach(link => {
                    if (link.getAttribute('href')) {
                        const baseUrl = link.getAttribute('href').split('?')[0];
                        link.href = baseUrl + '?next=' + nextUrl;
                    }
                });

                modal.classList.add('active');
                document.body.style.overflow = 'hidden';
            }
        }
    });
});

// ==========================================
// FEEDBACK FORM HANDLER
// ==========================================

document.addEventListener('DOMContentLoaded', () => {
    const feedbackForm = document.getElementById('feedback-form');

    if (feedbackForm) {
        feedbackForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            const submitBtn = feedbackForm.querySelector('button[type="submit"]');
            const originalText = submitBtn.innerHTML;

            // Disable button
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<svg class="animate-spin h-5 w-5 mx-auto" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>';

            try {
                const formData = new FormData(feedbackForm);
                const response = await fetch(feedbackForm.dataset.url, {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });

                const data = await response.json();

                // Закрыть форму
                document.getElementById('modal-feedback').classList.remove('active');

                if (data.success) {
                    // Показать успех
                    document.getElementById('modal-feedback-success').classList.add('active');
                    feedbackForm.reset();
                } else {
                    // Показать ошибку
                    document.getElementById('modal-feedback-error').classList.add('active');
                }
            } catch (error) {
                document.getElementById('modal-feedback').classList.remove('active');
                document.getElementById('modal-feedback-error').classList.add('active');
            } finally {
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalText;
            }
        });
    }

    // Retry button
    const retryBtn = document.getElementById('btn-retry-feedback');
    if (retryBtn) {
        retryBtn.addEventListener('click', () => {
            document.getElementById('modal-feedback-error').classList.remove('active');
            document.getElementById('modal-feedback').classList.add('active');
        });
    }
});


// ==========================================
// USER MENU DROPDOWN
// ==========================================

document.addEventListener('DOMContentLoaded', () => {
    const userMenuToggle = document.getElementById('user-menu-toggle');
    const userMenuDropdown = document.getElementById('user-menu-dropdown');
    const userMenuArrow = document.getElementById('user-menu-arrow');

    if (userMenuToggle && userMenuDropdown) {
        userMenuToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            userMenuDropdown.classList.toggle('hidden');
            if (userMenuArrow) {
                userMenuArrow.classList.toggle('rotate-180');
            }
        });

        // Close on outside click
        document.addEventListener('click', (e) => {
            if (!userMenuToggle.contains(e.target) && !userMenuDropdown.contains(e.target)) {
                userMenuDropdown.classList.add('hidden');
                if (userMenuArrow) {
                    userMenuArrow.classList.remove('rotate-180');
                }
            }
        });
    }
});

// ==========================================
// SCROLL REVEAL ANIMATION
// ==========================================

document.addEventListener('DOMContentLoaded', () => {
    const revealCards = document.querySelectorAll('.reveal-card');

    if (revealCards.length === 0) return;

    const observerOptions = {
        root: null,
        rootMargin: '0px 0px -50px 0px', // Триггер когда элемент на 50px выше нижней границы экрана
        threshold: 0.1
    };

    const revealObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('revealed');
                // Отключить наблюдение после появления (анимация один раз)
                revealObserver.unobserve(entry.target);
            }
        });
    }, observerOptions);

    revealCards.forEach(card => {
        revealObserver.observe(card);
    });
});


// ==========================================
// CAR SLIDER WITH PRELOAD
// ==========================================

document.addEventListener('DOMContentLoaded', () => {
    const sliderContainer = document.querySelector('.car-slider-container');
    if (!sliderContainer) return;

    const slides = sliderContainer.querySelectorAll('.car-slide');
    if (slides.length < 2) return;

    let currentIndex = 0;
    const intervalTime = 4000; // 4 секунды между сменой

    // Функция предзагрузки всех изображений
    function preloadImages() {
        return new Promise((resolve) => {
            let loadedCount = 0;
            const totalImages = slides.length;

            slides.forEach((img) => {
                // Если уже загружена
                if (img.complete && img.naturalHeight !== 0) {
                    loadedCount++;
                    if (loadedCount === totalImages) resolve();
                } else {
                    img.addEventListener('load', () => {
                        loadedCount++;
                        if (loadedCount === totalImages) resolve();
                    }, { once: true });

                    img.addEventListener('error', () => {
                        loadedCount++;
                        if (loadedCount === totalImages) resolve();
                    }, { once: true });
                }
            });

            // Fallback если картинки уже в кеше
            if (loadedCount === totalImages) resolve();
        });
    }

    // Смена слайда
    function nextSlide() {
        slides[currentIndex].classList.remove('active');
        currentIndex = (currentIndex + 1) % slides.length;
        slides[currentIndex].classList.add('active');
    }

    // Запуск после загрузки всех картинок
    preloadImages().then(() => {
        sliderContainer.classList.add('loaded');

        // Убедиться что первый слайд активен
        slides.forEach((slide, index) => {
            slide.classList.toggle('active', index === 0);
        });

        // Запустить автосмену
        setInterval(nextSlide, intervalTime);
    });
});
/**
 * A2M Digital Solutions - Main JavaScript
 * Handles navigation, form submission (FastAPI Backend), WhatsApp, animations, and interactions
 */

(function() {
    'use strict';

    // ========================================
    // Backend API Configuration
    // ========================================
    // UPDATE THIS TO YOUR DEPLOYED BACKEND URL
    // Examples:
    // - Local: 'http://localhost:8000'
    // - Render: 'https://a2m-digital-solutions-api.onrender.com'
    // - Railway: 'https://a2m-digital-solutions-api.up.railway.app'
    // - Fly.io: 'https://a2m-digital-solutions-api.fly.dev'
    const API_BASE_URL = '';  // Change for production!

    // ========================================
    // WhatsApp Configuration
    // ========================================
    const WHATSAPP_NUMBER = '918208214218';  // Your WhatsApp number with country code (no +)

    // ========================================
    // DOM Elements
    // ========================================
    const navbar = document.getElementById('navbar');
    const navMenu = document.getElementById('nav-menu');
    const navToggle = document.getElementById('nav-toggle');
    const navLinks = document.querySelectorAll('.nav-link');
    const inquiryForm = document.getElementById('inquiry-form');
    const successModal = document.getElementById('success-modal');
    const closeModalBtn = document.getElementById('close-modal');
    const scrollIndicator = document.querySelector('.scroll-indicator');

    // ========================================
    // Navigation
    // ========================================

    // Toggle mobile menu
    function toggleMobileMenu() {
        navMenu.classList.toggle('active');
        navToggle.classList.toggle('active');
        document.body.style.overflow = navMenu.classList.contains('active') ? 'hidden' : '';
    }

    navToggle.addEventListener('click', toggleMobileMenu);

    // Close mobile menu when clicking a link
    navLinks.forEach(link => {
        link.addEventListener('click', () => {
            if (navMenu.classList.contains('active')) {
                toggleMobileMenu();
            }
        });
    });

    // Close mobile menu when clicking outside
    document.addEventListener('click', (e) => {
        if (navMenu.classList.contains('active') &&
            !navMenu.contains(e.target) &&
            !navToggle.contains(e.target)) {
            toggleMobileMenu();
        }
    });

    // Navbar scroll effect
    let lastScrollY = window.scrollY;
    function handleNavbarScroll() {
        const currentScrollY = window.scrollY;

        if (currentScrollY > 50) {
            navbar.classList.add('scrolled');
        } else {
            navbar.classList.remove('scrolled');
        }

        lastScrollY = currentScrollY;
    }

    window.addEventListener('scroll', handleNavbarScroll, { passive: true });

    // Smooth scroll for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            const targetId = this.getAttribute('href');
            if (targetId === '#') return;

            const target = document.querySelector(targetId);
            if (target) {
                e.preventDefault();
                const offset = navbar.offsetHeight;
                const targetPosition = target.getBoundingClientRect().top + window.scrollY - offset;

                window.scrollTo({
                    top: targetPosition,
                    behavior: 'smooth'
                });

                // If scrolling to contact form, pre-select service from data attribute
                if (targetId === '#contact' || targetId === '#inquiry') {
                    const service = this.dataset.service;
                    if (service) {
                        setTimeout(() => {
                            const serviceSelect = document.getElementById('service');
                            if (serviceSelect) {
                                serviceSelect.value = service;
                                serviceSelect.focus();
                            }
                        }, 500); // Wait for scroll to complete
                    }
                }
            }
        });
    });

    // ========================================
    // Form Handling
    // ========================================

    // Form validation
    function validateForm(form) {
        let isValid = true;
        const requiredFields = form.querySelectorAll('[required]');

        requiredFields.forEach(field => {
            const formGroup = field.closest('.form-group');
            const errorMsg = formGroup.querySelector('.form-error') || createErrorElement(formGroup);

            if (!field.value.trim()) {
                showError(field, formGroup, errorMsg, 'This field is required');
                isValid = false;
            } else if (field.type === 'email' && !isValidEmail(field.value)) {
                showError(field, formGroup, errorMsg, 'Please enter a valid email address');
                isValid = false;
            } else if (field.type === 'tel' && field.value && !isValidPhone(field.value)) {
                showError(field, formGroup, errorMsg, 'Please enter a valid phone number');
                isValid = false;
            } else {
                clearError(field, formGroup, errorMsg);
            }
        });

        return isValid;
    }

    function createErrorElement(formGroup) {
        const error = document.createElement('span');
        error.className = 'form-error';
        formGroup.appendChild(error);
        return error;
    }

    function showError(field, formGroup, errorMsg, message) {
        field.classList.add('error');
        formGroup.classList.add('has-error');
        errorMsg.textContent = message;
    }

    function clearError(field, formGroup, errorMsg) {
        field.classList.remove('error');
        formGroup.classList.remove('has-error');
        errorMsg.textContent = '';
    }

    function isValidEmail(email) {
        const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return re.test(email);
    }

    function isValidPhone(phone) {
        const re = /^[\+]?[(]?[0-9]{1,3}[)]?[-\s\.]?[(]?[0-9]{1,3}[)]?[-\s\.]?[0-9]{4,6}$/;
        return re.test(phone.replace(/\s/g, ''));
    }

    // Real-time validation
    inquiryForm.querySelectorAll('input, select, textarea').forEach(field => {
        field.addEventListener('blur', () => validateField(field));
        field.addEventListener('input', () => {
            if (field.classList.contains('error')) {
                validateField(field);
            }
        });
    });

    function validateField(field) {
        const formGroup = field.closest('.form-group');
        const errorMsg = formGroup.querySelector('.form-error') || createErrorElement(formGroup);

        if (field.hasAttribute('required') && !field.value.trim()) {
            showError(field, formGroup, errorMsg, 'This field is required');
            return false;
        } else if (field.type === 'email' && field.value && !isValidEmail(field.value)) {
            showError(field, formGroup, errorMsg, 'Please enter a valid email address');
            return false;
        } else if (field.type === 'tel' && field.value && !isValidPhone(field.value)) {
            showError(field, formGroup, errorMsg, 'Please enter a valid phone number');
            return false;
        } else {
            clearError(field, formGroup, errorMsg);
            return true;
        }
    }

    // Form submission with FastAPI Backend
    async function handleFormSubmit(e) {
        e.preventDefault();

        if (!validateForm(inquiryForm)) {
            // Scroll to first error
            const firstError = inquiryForm.querySelector('.error');
            if (firstError) {
                firstError.focus();
                firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
            return;
        }

        const submitBtn = inquiryForm.querySelector('button[type="submit"]');
        const originalText = submitBtn.textContent;

        // Show loading state
        submitBtn.classList.add('loading');
        submitBtn.disabled = true;
        submitBtn.textContent = 'Sending...';

        try {
            const formData = new FormData(inquiryForm);
            const data = Object.fromEntries(formData.entries());

            // Send to FastAPI backend
            const response = await fetch(`${API_BASE_URL}/api/inquiries`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(data)
            });

            const result = await response.json();

            if (!response.ok) {
                // Handle validation errors from backend
                if (response.status === 422 && result.detail) {
                    const errors = result.detail;
                    if (Array.isArray(errors)) {
                        errors.forEach(err => {
                            const fieldName = err.loc?.[1];
                            const message = err.msg;
                            if (fieldName) {
                                const field = inquiryForm.querySelector(`[name="${fieldName}"]`);
                                if (field) {
                                    const formGroup = field.closest('.form-group');
                                    const errorMsg = formGroup.querySelector('.form-error') || createErrorElement(formGroup);
                                    showError(field, formGroup, errorMsg, message);
                                }
                            }
                        });
                    }
                }
                throw new Error(result.detail || `Server error: ${response.status}`);
            }

            console.log('Inquiry submitted:', result);

            // Show success modal
            showSuccessModal();

            // Reset form
            inquiryForm.reset();

        } catch (error) {
            console.error('Form submission error:', error);

            // Show user-friendly error
            let errorMessage = 'Failed to send inquiry. Please try again.';
            if (error.message) {
                errorMessage += ' (' + error.message + ')';
            }
            alert(errorMessage);
        } finally {
            submitBtn.classList.remove('loading');
            submitBtn.disabled = false;
            submitBtn.textContent = originalText;
        }
    }

    inquiryForm.addEventListener('submit', handleFormSubmit);

    // Success modal
    function showSuccessModal() {
        successModal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    function hideSuccessModal() {
        successModal.classList.remove('active');
        document.body.style.overflow = '';
    }

    closeModalBtn.addEventListener('click', hideSuccessModal);

    // Close modal on backdrop click
    successModal.addEventListener('click', (e) => {
        if (e.target === successModal) {
            hideSuccessModal();
        }
    });

    // Close modal on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && successModal.classList.contains('active')) {
            hideSuccessModal();
        }
    });

    // ========================================
    // WhatsApp Integration
    // ========================================
    const whatsappBtn = document.getElementById('submit-whatsapp');
    if (whatsappBtn) {
        whatsappBtn.addEventListener('click', function(e) {
            e.preventDefault();

            if (!validateForm(inquiryForm)) {
                const firstError = inquiryForm.querySelector('.error');
                if (firstError) {
                    firstError.focus();
                    firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
                return;
            }

            const formData = Object.fromEntries(new FormData(inquiryForm).entries());
            sendWhatsAppInquiry(formData);

            // Show success modal
            showSuccessModal(formData);

            // Reset form
            inquiryForm.reset();
        });
    }

    // Helper functions to convert form values to readable labels
    function getServiceLabel(value) {
        const services = {
            'web-development': 'Web Development',
            'mobile-app': 'Mobile App Development',
            'backend': 'Backend Development',
            'ui-ux': 'UI/UX Design',
            'devops': 'DevOps & Maintenance',
            'consultation': 'Consultation & Strategy',
            'ai-agent': 'AI Agent Development',
            'other': 'Other'
        };
        return services[value] || value;
    }

    function getBudgetLabel(value) {
        const budgets = {
            'under-5k': 'Under $5,000',
            '5k-15k': '$5,000 - $15,000',
            '15k-30k': '$15,000 - $30,000',
            '30k-50k': '$30,000 - $50,000',
            '50k-plus': '$50,000+',
            'not-sure': 'Not sure yet'
        };
        return budgets[value] || value || 'Not specified';
    }

    function getTimelineLabel(value) {
        const timelines = {
            'asap': 'ASAP',
            '1-2-months': '1-2 Months',
            '3-6-months': '3-6 Months',
            '6-months-plus': '6+ Months',
            'flexible': 'Flexible'
        };
        return timelines[value] || value || 'Not specified';
    }

    // WhatsApp Integration
    function sendWhatsAppInquiry(formData) {
        const message = `*New Project Inquiry - A2M Digital Solutions*

*Name:* ${formData.name}
*Email:* ${formData.email}
*Phone:* ${formData.phone || 'Not provided'}
*Service:* ${getServiceLabel(formData.service)}
*Timeline:* ${getTimelineLabel(formData.timeline)}

*Project Details:*
${formData.message}`;

        const encodedMessage = encodeURIComponent(message);
        const whatsappUrl = `https://wa.me/${WHATSAPP_NUMBER}?text=${encodedMessage}`;

        // Open in new tab
        window.open(whatsappUrl, '_blank', 'noopener,noreferrer');
    }

    // Success modal
    function showSuccessModal(formData) {
        successModal.classList.add('active');
        document.body.style.overflow = 'hidden';

        // Also send via WhatsApp (non-blocking)
        if (formData) {
            setTimeout(() => sendWhatsAppInquiry(formData), 500);
        }
    }

    function hideSuccessModal() {
        successModal.classList.remove('active');
        document.body.style.overflow = '';
    }

    closeModalBtn.addEventListener('click', hideSuccessModal);

    // Close modal on backdrop click
    successModal.addEventListener('click', (e) => {
        if (e.target === successModal) {
            hideSuccessModal();
        }
    });

    // Close modal on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && successModal.classList.contains('active')) {
            hideSuccessModal();
        }
    });

    // ========================================
    // Scroll Animations
    // ========================================

    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                observer.unobserve(entry.target);
            }
        });
    }, observerOptions);

    // Observe elements for fade-in animation
    document.querySelectorAll('.service-card, .process-step, .value, .contact-item').forEach(el => {
        el.classList.add('fade-in');
        observer.observe(el);
    });

    // ========================================
    // Hero Cards Animation
    // ========================================
    const heroCards = document.querySelectorAll('.hero-card');
    heroCards.forEach((card, index) => {
        card.style.animationDelay = `${0.5 + index * 0.1}s`;
    });

    // ========================================
    // Parallax Effect (Subtle)
    // ========================================
    let ticking = false;
    function updateParallax() {
        const scrolled = window.scrollY;
        const heroBackground = document.querySelector('.hero-background');

        if (heroBackground && scrolled < window.innerHeight) {
            heroBackground.style.transform = `translateY(${scrolled * 0.3}px)`;
        }

        ticking = false;
    }

    window.addEventListener('scroll', () => {
        if (!ticking) {
            requestAnimationFrame(updateParallax);
            ticking = true;
        }
    }, { passive: true });

    // ========================================
    // Active Nav Link on Scroll
    // ========================================
    const sections = document.querySelectorAll('section[id]');
    const navLinkMap = {};

    navLinks.forEach(link => {
        const href = link.getAttribute('href');
        if (href.startsWith('#')) {
            navLinkMap[href.slice(1)] = link;
        }
    });

    function updateActiveNavLink() {
        const scrollPos = window.scrollY + navbar.offsetHeight + 100;

        sections.forEach(section => {
            const sectionTop = section.offsetTop;
            const sectionHeight = section.offsetHeight;
            const sectionId = section.getAttribute('id');

            if (scrollPos >= sectionTop && scrollPos < sectionTop + sectionHeight) {
                navLinks.forEach(l => l.classList.remove('active'));
                if (navLinkMap[sectionId]) {
                    navLinkMap[sectionId].classList.add('active');
                }
            }
        });
    }

    window.addEventListener('scroll', updateActiveNavLink, { passive: true });

    // ========================================
    // Initialize
    // ========================================
    function init() {
        // Initial navbar state
        handleNavbarScroll();

        // Initial active nav link
        updateActiveNavLink();

        // Add smooth reveal to hero elements
        const heroElements = document.querySelectorAll('.hero-content > *');
        heroElements.forEach((el, index) => {
            el.style.opacity = '0';
            el.style.transform = 'translateY(30px)';
            el.style.transition = `all 0.8s ease ${index * 0.1}s`;
        });

        // Trigger hero animation
        requestAnimationFrame(() => {
            heroElements.forEach(el => {
                el.style.opacity = '1';
                el.style.transform = 'translateY(0)';
            });
        });

        console.log('A2M Digital Solutions - Website initialized');
        console.log('API Base URL:', API_BASE_URL);
    }

    // Run init when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
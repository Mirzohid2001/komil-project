(function () {
  'use strict';

  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function hideLoader() {
    var el = document.querySelector('.page-loader');
    if (el) el.classList.add('loader-hidden');
  }

  function reveal() {
    if (reduce) {
      document.querySelectorAll('.zl-reveal, .zl-stagger').forEach(function (n) {
        n.classList.add('is-in');
      });
      return;
    }
    if (!('IntersectionObserver' in window)) {
      document.querySelectorAll('.zl-reveal, .zl-stagger').forEach(function (n) {
        n.classList.add('is-in');
      });
      return;
    }
    // threshold 0: tall lists (e.g. 30+ tests) never reach 0.12 ratio
    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting || entry.intersectionRatio > 0) {
            entry.target.classList.add('is-in');
            io.unobserve(entry.target);
          }
        });
      },
      { rootMargin: '40px 0px 40px 0px', threshold: 0 }
    );
    document.querySelectorAll('.zl-reveal, .zl-stagger').forEach(function (n) {
      io.observe(n);
      // Already in view on load (tall containers / above-fold)
      var rect = n.getBoundingClientRect();
      if (rect.top < window.innerHeight && rect.bottom > 0) {
        n.classList.add('is-in');
        io.unobserve(n);
      }
    });
  }

  function parallaxHero() {
    if (reduce) return;
    var heroes = document.querySelectorAll('[data-zl-parallax]');
    if (!heroes.length) return;

    var ticking = false;
    function update() {
      ticking = false;
      var y = window.scrollY || 0;
      heroes.forEach(function (hero) {
        var rect = hero.getBoundingClientRect();
        if (rect.bottom < 0 || rect.top > window.innerHeight) return;
        var shift = Math.min(28, Math.max(-12, y * 0.08));
        var orbs = hero.querySelectorAll('.zl-orb');
        orbs.forEach(function (orb, i) {
          orb.style.transform = 'translateY(' + shift * (i === 0 ? 0.6 : -0.4) + 'px)';
        });
        var grid = hero.querySelector('.zl-hero-grid');
        if (grid) grid.style.transform = 'translateY(' + shift * 0.35 + 'px)';
      });
    }

    window.addEventListener(
      'scroll',
      function () {
        if (!ticking) {
          ticking = true;
          requestAnimationFrame(update);
        }
      },
      { passive: true }
    );
    update();
  }

  function magneticButtons() {
    if (reduce || window.innerWidth < 900) return;
    document.querySelectorAll('[data-zl-magnetic]').forEach(function (btn) {
      btn.addEventListener('mousemove', function (e) {
        var r = btn.getBoundingClientRect();
        var x = e.clientX - r.left - r.width / 2;
        var y = e.clientY - r.top - r.height / 2;
        btn.style.transform = 'translate(' + x * 0.12 + 'px,' + y * 0.18 + 'px)';
      });
      btn.addEventListener('mouseleave', function () {
        btn.style.transform = '';
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    reveal();
    parallaxHero();
    magneticButtons();
  });

  window.addEventListener('load', hideLoader);
})();

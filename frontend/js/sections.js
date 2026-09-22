/**
 * Scroll choreography and interaction for the experience sections.
 * Assumes GSAP + ScrollTrigger are already on the page.
 */

const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function money(value) {
  if (value === null || value === undefined) return "Not reported";
  return "$" + Math.round(value).toLocaleString();
}

export function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value === null || value === undefined ? "" : value;
  return div.innerHTML;
}

/** Fades sections up as they enter the viewport. */
export function revealOnScroll() {
  if (!window.gsap || reduced) {
    document.querySelectorAll("[data-rise]").forEach(function (el) {
      el.style.opacity = 1;
      el.style.transform = "none";
    });
    return;
  }

  gsap.utils.toArray("[data-rise]").forEach(function (el) {
    gsap.fromTo(el,
      { opacity: 0, y: 40 },
      {
        opacity: 1,
        y: 0,
        duration: 1,
        ease: "power3.out",
        scrollTrigger: { trigger: el, start: "top 86%" }
      }
    );
  });
}

/** Preference orbs: select, glow, and draw a line to the centre. */
export function initOrbs() {
  const orbs = document.querySelectorAll(".orb");
  const summary = document.getElementById("orb-summary");
  const chosen = new Set();

  orbs.forEach(function (orb, index) {
    // Distribute the orbs evenly around the profile core.
    const angle = (index / orbs.length) * Math.PI * 2 - Math.PI / 2;
    const radius = window.innerWidth < 820 ? 132 : 220;

    orb.style.setProperty("--ox", Math.cos(angle) * radius + "px");
    orb.style.setProperty("--oy", Math.sin(angle) * radius + "px");
    orb.style.setProperty("--delay", (index * 0.08).toFixed(2) + "s");

    orb.addEventListener("click", function () {
      orb.classList.toggle("is-on");

      if (orb.classList.contains("is-on")) {
        chosen.add(orb.dataset.label);
      } else {
        chosen.delete(orb.dataset.label);
      }

      if (window.gsap && !reduced) {
        gsap.fromTo(orb,
          { scale: 1 },
          { scale: 1.16, duration: 0.22, yoyo: true, repeat: 1, ease: "power2.out" }
        );
      }

      summary.textContent = chosen.size
        ? Array.from(chosen).join("  ·  ")
        : "Select what matters to you";
    });
  });
}

/** Course chips feed straight into the real preferences page. */
export function initCourseChips() {
  document.querySelectorAll(".course-chip").forEach(function (chip) {
    chip.addEventListener("click", function () {
      document.querySelectorAll(".course-chip").forEach(function (other) {
        other.classList.remove("is-on");
      });
      chip.classList.add("is-on");

      const target = document.getElementById("course-cta");
      if (target) {
        target.href = "preferences.html?field=" +
          encodeURIComponent(chip.dataset.course);
        target.textContent = "Find " + chip.dataset.course + " universities →";
      }
    });
  });
}

/** Animates the AI pipeline stages in sequence. */
export function initPipeline() {
  const stages = document.querySelectorAll(".stage");
  if (!stages.length || !window.gsap || reduced) {
    stages.forEach(function (s) { s.classList.add("is-on"); });
    return;
  }

  ScrollTrigger.create({
    trigger: "#advisor",
    start: "top 60%",
    once: true,
    onEnter: function () {
      stages.forEach(function (stage, index) {
        gsap.delayedCall(index * 0.45, function () {
          stage.classList.add("is-on");
        });
      });
    }
  });
}

/**
 * Circular match dial plus the per-dimension bars.
 * Values are supplied by the caller so nothing here invents a score.
 */
export function initMatchDial(breakdown) {
  const ring = document.getElementById("match-ring");
  const value = document.getElementById("match-value");
  if (!ring || !value) return;

  const circumference = 2 * Math.PI * 86;
  ring.style.strokeDasharray = circumference;
  ring.style.strokeDashoffset = circumference;

  const overall = Math.round(
    breakdown.reduce(function (sum, item) { return sum + item.score; }, 0) /
    breakdown.length
  );

  const bars = document.getElementById("match-bars");
  bars.innerHTML = breakdown.map(function (item) {
    return '<div class="match-bar">' +
      '<span class="match-bar-label">' + escapeHtml(item.label) + "</span>" +
      '<span class="match-bar-track"><i data-score="' + item.score + '"></i></span>' +
      '<span class="match-bar-value">' + item.score + "%</span>" +
      "</div>";
  }).join("");

  function run() {
    if (!window.gsap || reduced) {
      value.textContent = overall + "%";
      ring.style.strokeDashoffset = circumference * (1 - overall / 100);
      bars.querySelectorAll("i").forEach(function (fill) {
        fill.style.width = fill.dataset.score + "%";
      });
      return;
    }

    gsap.to(ring, {
      strokeDashoffset: circumference * (1 - overall / 100),
      duration: 1.9,
      ease: "power3.out"
    });

    const counter = { n: 0 };
    gsap.to(counter, {
      n: overall,
      duration: 1.9,
      ease: "power3.out",
      onUpdate: function () {
        value.textContent = Math.round(counter.n) + "%";
      }
    });

    bars.querySelectorAll("i").forEach(function (fill, index) {
      gsap.to(fill, {
        width: fill.dataset.score + "%",
        duration: 1.3,
        delay: 0.25 + index * 0.1,
        ease: "power2.out"
      });
    });
  }

  if (window.ScrollTrigger) {
    ScrollTrigger.create({ trigger: "#match", start: "top 65%", once: true, onEnter: run });
  } else {
    run();
  }
}

/** Subtle pointer tilt on the glass recommendation cards. */
export function initCardTilt(container) {
  container.addEventListener("pointermove", function (event) {
    const card = event.target.closest(".glass-card");
    if (!card || reduced) return;

    const bounds = card.getBoundingClientRect();
    const x = (event.clientX - bounds.left) / bounds.width - 0.5;
    const y = (event.clientY - bounds.top) / bounds.height - 0.5;

    card.style.transform =
      "perspective(900px) rotateY(" + (x * 7).toFixed(2) + "deg) rotateX(" +
      (-y * 7).toFixed(2) + "deg) translateY(-4px)";
  });

  container.addEventListener("pointerleave", function () {
    container.querySelectorAll(".glass-card").forEach(function (card) {
      card.style.transform = "";
    });
  });
}

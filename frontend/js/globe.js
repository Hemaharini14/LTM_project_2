import * as THREE from "../vendor/three.module.js";

/**
 * Interactive university explorer.
 *
 * Every marker is a real institution at its real coordinates, joined
 * from the world-cities table — none of these points are decorative.
 */

const RADIUS = 5;

const COLOR_OCEAN = 0x0b1733;
const COLOR_GRID = 0x2f5590;
const COLOR_CYAN = 0x35d6ff;
const COLOR_GOLD = 0xe3b552;
const COLOR_VIOLET = 0x6d4df6;

/** Latitude/longitude to a point on the sphere. */
function toVector(latitude, longitude, radius) {
  const r = radius || RADIUS;
  const phi = (90 - latitude) * (Math.PI / 180);
  const theta = (longitude + 180) * (Math.PI / 180);

  return new THREE.Vector3(
    -r * Math.sin(phi) * Math.cos(theta),
    r * Math.cos(phi),
    r * Math.sin(phi) * Math.sin(theta)
  );
}

export function initGlobe(canvas, universities, onSelect) {
  const mobile = window.matchMedia("(max-width: 820px)").matches;

  const renderer = new THREE.WebGLRenderer({
    canvas: canvas,
    antialias: !mobile,
    alpha: true
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
  camera.position.set(0, 1.4, 14.5);

  scene.add(new THREE.AmbientLight(0x4a5a8f, 1.9));

  const key = new THREE.DirectionalLight(0x9fd8ff, 2.4);
  key.position.set(6, 5, 9);
  scene.add(key);

  const rim = new THREE.PointLight(COLOR_VIOLET, 60, 40);
  rim.position.set(-8, -2, -6);
  scene.add(rim);

  const world = new THREE.Group();
  scene.add(world);

  const oceanMaterial = new THREE.MeshStandardMaterial({
    color: COLOR_OCEAN,
    metalness: 0.35,
    roughness: 0.88
  });

  world.add(new THREE.Mesh(
    new THREE.SphereGeometry(RADIUS - 0.04, 64, 64),
    oceanMaterial
  ));

  const gridMaterial = new THREE.MeshBasicMaterial({
    color: COLOR_GRID,
    wireframe: true,
    transparent: true,
    opacity: 0.2
  });

  world.add(new THREE.Mesh(
    new THREE.SphereGeometry(RADIUS, 36, 24),
    gridMaterial
  ));

  const haloMaterial = new THREE.MeshBasicMaterial({
    color: COLOR_CYAN,
    transparent: true,
    opacity: 0.07,
    side: THREE.BackSide
  });

  scene.add(new THREE.Mesh(
    new THREE.SphereGeometry(RADIUS * 1.16, 48, 48),
    haloMaterial
  ));

  // ---- markers --------------------------------------------------------
  const markerGroup = new THREE.Group();
  world.add(markerGroup);

  const markerGeometry = new THREE.SphereGeometry(0.062, 10, 10);

  const usMaterial = new THREE.MeshBasicMaterial({ color: COLOR_CYAN });
  const intlMaterial = new THREE.MeshBasicMaterial({ color: COLOR_GOLD });

  const markers = [];

  universities.forEach(function (university) {
    const material = university.source === "us" ? usMaterial : intlMaterial;
    const marker = new THREE.Mesh(markerGeometry, material);

    marker.position.copy(
      toVector(university.latitude, university.longitude, RADIUS + 0.03)
    );
    marker.userData = university;

    markerGroup.add(marker);
    markers.push(marker);
  });

  // A slightly larger ring that snaps to whichever marker is hovered.
  const highlight = new THREE.Mesh(
    new THREE.RingGeometry(0.1, 0.14, 24),
    new THREE.MeshBasicMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: 0.9,
      side: THREE.DoubleSide
    })
  );
  highlight.visible = false;
  world.add(highlight);

  // ---- interaction -----------------------------------------------------
  const raycaster = new THREE.Raycaster();
  raycaster.params.Points = { threshold: 0.1 };

  const pointer = new THREE.Vector2(-2, -2);

  const drag = {
    active: false,
    lastX: 0,
    velocity: 0,
    rotation: 0
  };

  let hovered = null;
  let autoSpin = true;

  function setPointerFromEvent(event) {
    const bounds = canvas.getBoundingClientRect();
    pointer.x = ((event.clientX - bounds.left) / bounds.width) * 2 - 1;
    pointer.y = -((event.clientY - bounds.top) / bounds.height) * 2 + 1;
  }

  canvas.addEventListener("pointerdown", function (event) {
    drag.active = true;
    drag.lastX = event.clientX;
    autoSpin = false;
    canvas.setPointerCapture(event.pointerId);
  });

  canvas.addEventListener("pointerup", function (event) {
    drag.active = false;
    canvas.releasePointerCapture(event.pointerId);
  });

  canvas.addEventListener("pointerleave", function () {
    drag.active = false;
    autoSpin = true;
    pointer.set(-2, -2);
  });

  canvas.addEventListener("pointermove", function (event) {
    setPointerFromEvent(event);

    if (drag.active) {
      drag.velocity = (event.clientX - drag.lastX) * 0.005;
      drag.rotation += drag.velocity;
      drag.lastX = event.clientX;
    }
  });

  canvas.addEventListener("click", function (event) {
    setPointerFromEvent(event);

    raycaster.setFromCamera(pointer, camera);
    const hits = raycaster.intersectObjects(markers, false);

    if (hits.length && onSelect) {
      onSelect(hits[0].object.userData);
    }
  });

  // ---- loop -------------------------------------------------------------
  const clock = new THREE.Clock();
  let hoverCallback = null;

  canvas.addEventListener("webglcontextlost", function (event) {
    event.preventDefault();
  });

  canvas.addEventListener("webglcontextrestored", function () {
    resize();
  });

  function resize() {
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;

    // Layout may not have settled when the module first runs; skip
    // until the element actually has a box, then the observer retries.
    if (!width || !height) return;

    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }

  window.addEventListener("resize", resize);

  if (window.ResizeObserver) {
    new ResizeObserver(resize).observe(canvas);
  }

  requestAnimationFrame(resize);

  function frame() {
    const elapsed = clock.getElapsedTime();

    if (autoSpin && !drag.active) {
      drag.rotation += 0.0016;
    }

    world.rotation.y = drag.rotation;
    world.rotation.x = -0.22;

    // Hover detection
    raycaster.setFromCamera(pointer, camera);
    const hits = raycaster.intersectObjects(markers, false);
    const next = hits.length ? hits[0].object : null;

    if (next !== hovered) {
      hovered = next;

      if (hovered) {
        highlight.visible = true;
        highlight.position.copy(hovered.position).multiplyScalar(1.02);
        highlight.lookAt(0, 0, 0);
        canvas.style.cursor = "pointer";
      } else {
        highlight.visible = false;
        canvas.style.cursor = "grab";
      }

      if (hoverCallback) {
        hoverCallback(hovered ? hovered.userData : null);
      }
    }

    if (highlight.visible) {
      const pulse = 1 + Math.sin(elapsed * 4) * 0.18;
      highlight.scale.setScalar(pulse);
    }

    renderer.render(scene, camera);
    requestAnimationFrame(frame);
  }

  frame();

  return {
    onHover: function (callback) {
      hoverCallback = callback;
    },
    /** Spins the globe so a given place faces the camera. */
    focus: function (latitude, longitude) {
      autoSpin = false;
      drag.rotation = -((longitude + 180) * (Math.PI / 180)) + Math.PI / 2;
    },
    resize: resize
  };
}

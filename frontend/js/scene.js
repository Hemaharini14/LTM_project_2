import * as THREE from "../vendor/three.module.js";

/**
 * Cinematic hero scene: a futuristic campus floating in a data field,
 * with a slowly turning globe behind it.
 *
 * Everything is built from geometry rather than loaded models, so there
 * are no assets to fetch and nothing to block behind a proxy.
 */

const PALETTE = {
  cyan: 0x35d6ff,
  violet: 0x6d4df6,
  gold: 0xe3b552,
  deep: 0x122152,
  fog: 0x060a18
};

export function webglAvailable() {
  try {
    const probe = document.createElement("canvas");
    return Boolean(
      window.WebGLRenderingContext &&
      (probe.getContext("webgl2") || probe.getContext("webgl"))
    );
  } catch {
    return false;
  }
}

export function initScene(canvas) {
  const mobile = window.matchMedia("(max-width: 820px)").matches;
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: !mobile,
    alpha: true,
    powerPreference: "high-performance"
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, mobile ? 1.5 : 2));
  renderer.setSize(window.innerWidth, window.innerHeight);

  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(PALETTE.fog, 0.035);

  const camera = new THREE.PerspectiveCamera(
    46, window.innerWidth / window.innerHeight, 0.1, 200
  );
  camera.position.set(0, 3.4, 15);

  // ---- lighting: cool key, violet rim, warm fill --------------------
  scene.add(new THREE.AmbientLight(0x2a3a6b, 1.6));

  const key = new THREE.DirectionalLight(PALETTE.cyan, 2.1);
  key.position.set(6, 11, 8);
  scene.add(key);

  const rim = new THREE.PointLight(PALETTE.violet, 90, 46);
  rim.position.set(-9, 4, -7);
  scene.add(rim);

  const warm = new THREE.PointLight(PALETTE.gold, 26, 30);
  warm.position.set(4, 1.2, 5);
  scene.add(warm);

  // ---- the campus ---------------------------------------------------
  const campus = new THREE.Group();
  // Set back and low so it reads as a distant floating island beneath
  // the type, rather than competing with it for the centre.
  campus.position.set(0, -6.2, -9);
  campus.scale.setScalar(0.82);
  scene.add(campus);

  const plate = new THREE.Mesh(
    new THREE.CylinderGeometry(5.6, 5.1, 0.34, 64),
    new THREE.MeshStandardMaterial({
      color: 0x0d1a3d,
      metalness: 0.85,
      roughness: 0.42,
      emissive: PALETTE.deep,
      emissiveIntensity: 0.5
    })
  );
  plate.position.y = -1.1;
  campus.add(plate);

  const plateRing = new THREE.Mesh(
    new THREE.TorusGeometry(5.62, 0.022, 10, 120),
    new THREE.MeshBasicMaterial({
      color: PALETTE.cyan,
      transparent: true,
      opacity: 0.75
    })
  );
  plateRing.rotation.x = Math.PI / 2;
  plateRing.position.y = -0.93;
  campus.add(plateRing);

  const towerMaterial = new THREE.MeshStandardMaterial({
    color: 0x16255a,
    metalness: 0.92,
    roughness: 0.22,
    emissive: 0x1b3a86,
    emissiveIntensity: 0.85
  });

  const edgeMaterial = new THREE.LineBasicMaterial({
    color: PALETTE.cyan,
    transparent: true,
    opacity: 0.68
  });

  const towers = [];

  const rings = [
    { count: 1, radius: 0, height: 4.6, width: 1.5 },
    { count: 6, radius: 2.3, height: 3.0, width: 0.92 },
    { count: 10, radius: 4.0, height: 1.9, width: 0.74 }
  ];

  rings.forEach((ring, ringIndex) => {
    for (let i = 0; i < ring.count; i++) {
      const angle = (i / ring.count) * Math.PI * 2 + ringIndex * 0.45;
      const height = ring.height * (0.72 + Math.random() * 0.56);
      const width = ring.width * (0.82 + Math.random() * 0.36);

      const geometry = new THREE.BoxGeometry(width, height, width);
      const tower = new THREE.Mesh(geometry, towerMaterial);
      tower.position.set(
        Math.cos(angle) * ring.radius,
        height / 2 - 0.9,
        Math.sin(angle) * ring.radius
      );
      tower.rotation.y = Math.random() * Math.PI;
      campus.add(tower);

      const edges = new THREE.LineSegments(
        new THREE.EdgesGeometry(geometry),
        edgeMaterial
      );
      edges.position.copy(tower.position);
      edges.rotation.copy(tower.rotation);
      campus.add(edges);

      // A lit crown so towers stay readable against the fog.
      const crown = new THREE.Mesh(
        new THREE.BoxGeometry(width * 0.34, 0.05, width * 0.34),
        new THREE.MeshBasicMaterial({
          color: ringIndex === 0 ? PALETTE.gold : PALETTE.cyan,
          transparent: true,
          opacity: 0.9
        })
      );
      crown.position.set(
        tower.position.x,
        tower.position.y + height / 2 + 0.05,
        tower.position.z
      );
      campus.add(crown);

      towers.push({ mesh: tower, crown, phase: Math.random() * Math.PI * 2 });
    }
  });

  // ---- background globe ---------------------------------------------
  const globe = new THREE.Group();
  globe.position.set(0.8, 4.2, -30);
  scene.add(globe);

  globe.add(new THREE.Mesh(
    new THREE.SphereGeometry(8.4, 48, 48),
    new THREE.MeshBasicMaterial({
      color: 0x0f1c47,
      transparent: true,
      opacity: 0.5
    })
  ));

  const globeWire = new THREE.Mesh(
    new THREE.SphereGeometry(8.45, 34, 26),
    new THREE.MeshBasicMaterial({
      color: PALETTE.cyan,
      wireframe: true,
      transparent: true,
      opacity: 0.14
    })
  );
  globe.add(globeWire);

  const markerCount = mobile ? 60 : 130;
  const markerPositions = new Float32Array(markerCount * 3);

  for (let i = 0; i < markerCount; i++) {
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    markerPositions[i * 3] = 8.5 * Math.sin(phi) * Math.cos(theta);
    markerPositions[i * 3 + 1] = 8.5 * Math.cos(phi);
    markerPositions[i * 3 + 2] = 8.5 * Math.sin(phi) * Math.sin(theta);
  }

  const markerGeometry = new THREE.BufferGeometry();
  markerGeometry.setAttribute(
    "position",
    new THREE.BufferAttribute(markerPositions, 3)
  );

  globe.add(new THREE.Points(markerGeometry, new THREE.PointsMaterial({
    color: PALETTE.gold,
    size: 0.17,
    transparent: true,
    opacity: 0.92,
    sizeAttenuation: true
  })));

  // ---- ambient data particles ---------------------------------------
  const particleCount = mobile ? 700 : 2200;
  const positions = new Float32Array(particleCount * 3);
  const drift = new Float32Array(particleCount);

  for (let i = 0; i < particleCount; i++) {
    positions[i * 3] = (Math.random() - 0.5) * 60;
    positions[i * 3 + 1] = (Math.random() - 0.5) * 34;
    positions[i * 3 + 2] = (Math.random() - 0.5) * 48 - 6;
    drift[i] = 0.1 + Math.random() * 0.5;
  }

  const particleGeometry = new THREE.BufferGeometry();
  particleGeometry.setAttribute(
    "position",
    new THREE.BufferAttribute(positions, 3)
  );

  const particles = new THREE.Points(particleGeometry, new THREE.PointsMaterial({
    color: 0x9fd8ff,
    size: 0.055,
    transparent: true,
    opacity: 0.62,
    sizeAttenuation: true,
    depthWrite: false
  }));
  scene.add(particles);

  // ---- orbiting academic markers -------------------------------------
  const orbiterGeometries = [
    new THREE.TetrahedronGeometry(0.19),
    new THREE.OctahedronGeometry(0.17),
    new THREE.TorusGeometry(0.14, 0.04, 8, 22)
  ];

  const orbiters = [];

  for (let i = 0; i < (mobile ? 4 : 8); i++) {
    const warmOne = i % 3 === 0;

    const mesh = new THREE.Mesh(
      orbiterGeometries[i % orbiterGeometries.length],
      new THREE.MeshStandardMaterial({
        color: warmOne ? PALETTE.gold : PALETTE.cyan,
        emissive: warmOne ? PALETTE.gold : PALETTE.cyan,
        emissiveIntensity: 0.85,
        metalness: 0.7,
        roughness: 0.3
      })
    );

    orbiters.push({
      mesh,
      radius: 9.2 + Math.random() * 3.4,
      height: -2.4 + Math.random() * 4.2,
      speed: 0.07 + Math.random() * 0.12,
      angle: Math.random() * Math.PI * 2,
      spin: 0.3 + Math.random() * 0.6
    });

    scene.add(mesh);
  }

  // ---- interaction and loop -------------------------------------------
  const pointer = { x: 0, y: 0, tx: 0, ty: 0 };

  window.addEventListener("pointermove", (event) => {
    pointer.tx = (event.clientX / window.innerWidth - 0.5) * 2;
    pointer.ty = (event.clientY / window.innerHeight - 0.5) * 2;
  });

  window.addEventListener("resize", () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });

  const state = { scroll: 0 };
  const clock = new THREE.Clock();

  function frame() {
    const elapsed = clock.getElapsedTime();

    if (!reduced) {
      campus.rotation.y = elapsed * 0.045;
      campus.position.y = -6.2 + Math.sin(elapsed * 0.55) * 0.16;
      plateRing.rotation.z = elapsed * 0.22;

      towers.forEach((tower, index) => {
        tower.crown.material.opacity =
          0.45 + Math.sin(elapsed * 1.6 + tower.phase) * 0.45;
        tower.mesh.scale.y = 1 + Math.sin(elapsed * 0.8 + index) * 0.012;
      });

      globe.rotation.y = elapsed * 0.035;
      globeWire.rotation.y = -elapsed * 0.018;

      orbiters.forEach((orbiter) => {
        orbiter.angle += orbiter.speed * 0.01;
        orbiter.mesh.position.set(
          Math.cos(orbiter.angle) * orbiter.radius,
          orbiter.height + Math.sin(elapsed * 0.7 + orbiter.angle) * 0.3,
          Math.sin(orbiter.angle) * orbiter.radius
        );
        orbiter.mesh.rotation.x += orbiter.spin * 0.01;
        orbiter.mesh.rotation.y += orbiter.spin * 0.013;
      });

      const points = particles.geometry.attributes.position.array;
      for (let i = 0; i < particleCount; i++) {
        points[i * 3 + 1] += drift[i] * 0.004;
        if (points[i * 3 + 1] > 17) points[i * 3 + 1] = -17;
      }
      particles.geometry.attributes.position.needsUpdate = true;
    }

    // Damped so the parallax never feels twitchy.
    pointer.x += (pointer.tx - pointer.x) * 0.045;
    pointer.y += (pointer.ty - pointer.y) * 0.045;

    camera.position.x = pointer.x * 1.5;
    camera.position.y = 2.4 - pointer.y * 0.7 - state.scroll * 4.0;
    camera.position.z = 15.5 - state.scroll * 5.0;
    camera.lookAt(0, -2.6 - state.scroll * 1.2, -4);

    renderer.render(scene, camera);
    requestAnimationFrame(frame);
  }

  frame();

  return {
    /** Scroll progress 0..1, driving the cinematic camera push-in. */
    setScroll(value) {
      state.scroll = value;
    }
  };
}

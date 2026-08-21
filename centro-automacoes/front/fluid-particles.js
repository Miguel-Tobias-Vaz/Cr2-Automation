(() => {
  /**
   * Fundo de partículas fluidas com interação do mouse.
  * Tema escuro Opto — partículas em dourado suave.
   */
  const PARTICLE_COUNT = 650;
  const NOISE_INTENSITY = 0.0025;
  const SIZE_MIN = 0.5;
  const SIZE_MAX = 1.65;
  const MOUSE_RADIUS = 160;
  const MOUSE_FORCE = 2.8;
  const MOUSE_WAKE = 0.55;

  function createNoise() {
    const permutation = [
      151, 160, 137, 91, 90, 15, 131, 13, 201, 95, 96, 53, 194, 233, 7, 225, 140,
      36, 103, 30, 69, 142, 8, 99, 37, 240, 21, 10, 23, 190, 6, 148, 247, 120,
      234, 75, 0, 26, 197, 62, 94, 252, 219, 203, 117, 35, 11, 32, 57, 177, 33,
      88, 237, 149, 56, 87, 174, 20, 125, 136, 171, 168, 68, 175, 74, 165, 71,
      134, 139, 48, 27, 166, 77, 146, 158, 231, 83, 111, 229, 122, 60, 211, 133,
      230, 220, 105, 92, 41, 55, 46, 245, 40, 244, 102, 143, 54, 65, 25, 63, 161,
      1, 216, 80, 73, 209, 76, 132, 187, 208, 89, 18, 169, 200, 196, 135, 130,
      116, 188, 159, 86, 164, 100, 109, 198, 173, 186, 3, 64, 52, 217, 226, 250,
      124, 123, 5, 202, 38, 147, 118, 126, 255, 82, 85, 212, 207, 206, 59, 227,
      47, 16, 58, 17, 182, 189, 28, 42, 223, 183, 170, 213, 119, 248, 152, 2, 44,
      154, 163, 70, 221, 153, 101, 155, 167, 43, 172, 9, 129, 22, 39, 253, 19, 98,
      108, 110, 79, 113, 224, 232, 178, 185, 112, 104, 218, 246, 97, 228, 251, 34,
      242, 193, 238, 210, 144, 12, 191, 179, 162, 241, 81, 51, 145, 235, 249, 14,
      239, 107, 49, 192, 214, 31, 181, 199, 106, 157, 184, 84, 204, 176, 115, 121,
      50, 45, 127, 4, 150, 254, 138, 236, 205, 93, 222, 114, 67, 29, 24, 72, 243,
      141, 128, 195, 78, 66, 215, 61, 156, 180,
    ];
    const p = new Array(512);
    for (let i = 0; i < 256; i++) p[256 + i] = p[i] = permutation[i];

    function fade(t) {
      return t * t * t * (t * (t * 6 - 15) + 10);
    }
    function lerp(t, a, b) {
      return a + t * (b - a);
    }
    function grad(hash, x, y, z) {
      const h = hash & 15;
      const u = h < 8 ? x : y;
      const v = h < 4 ? y : h === 12 || h === 14 ? x : z;
      return ((h & 1) === 0 ? u : -u) + ((h & 2) === 0 ? v : -v);
    }

    return {
      simplex3(x, y, z) {
        const X = Math.floor(x) & 255;
        const Y = Math.floor(y) & 255;
        const Z = Math.floor(z) & 255;
        x -= Math.floor(x);
        y -= Math.floor(y);
        z -= Math.floor(z);
        const u = fade(x);
        const v = fade(y);
        const w = fade(z);
        const A = p[X] + Y;
        const AA = p[A] + Z;
        const AB = p[A + 1] + Z;
        const B = p[X + 1] + Y;
        const BA = p[B] + Z;
        const BB = p[B + 1] + Z;
        return lerp(
          w,
          lerp(
            v,
            lerp(u, grad(p[AA], x, y, z), grad(p[BA], x - 1, y, z)),
            lerp(u, grad(p[AB], x, y - 1, z), grad(p[BB], x - 1, y - 1, z))
          ),
          lerp(
            v,
            lerp(
              u,
              grad(p[AA + 1], x, y, z - 1),
              grad(p[BA + 1], x - 1, y, z - 1)
            ),
            lerp(
              u,
              grad(p[AB + 1], x, y - 1, z - 1),
              grad(p[BB + 1], x - 1, y - 1, z - 1)
            )
          )
        );
      },
    };
  }

  let started = false;

  function initFluidBackground(options = {}) {
    if (started) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const count = options.particleCount || PARTICLE_COUNT;
    const noiseIntensity = options.noiseIntensity || NOISE_INTENSITY;
    const sizeMin = (options.particleSize && options.particleSize.min) || SIZE_MIN;
    const sizeMax = (options.particleSize && options.particleSize.max) || SIZE_MAX;
    const mouseRadius = options.mouseRadius || MOUSE_RADIUS;
    const mouseForce = options.mouseForce || MOUSE_FORCE;

    let canvas = document.getElementById("fluid-particles");
    if (!canvas) {
      canvas = document.createElement("canvas");
      canvas.id = "fluid-particles";
      canvas.className = "fluid-particles";
      canvas.setAttribute("aria-hidden", "true");
      document.body.prepend(canvas);
    }

    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) return;
    started = true;

    const noise = createNoise();
    let particles = [];

    const mouse = {
      x: -9999,
      y: -9999,
      vx: 0,
      vy: 0,
      px: -9999,
      py: -9999,
      active: false,
      strength: 0,
    };

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      canvas.width = Math.floor(window.innerWidth * dpr);
      canvas.height = Math.floor(window.innerHeight * dpr);
      canvas.style.width = "100%";
      canvas.style.height = "100%";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      spawn();
    };

    const spawn = () => {
      const w = window.innerWidth;
      const h = window.innerHeight;
      particles = Array.from({ length: count }, () => ({
        x: Math.random() * w,
        y: Math.random() * h,
        size: Math.random() * (sizeMax - sizeMin) + sizeMin,
        velocity: { x: 0, y: 0 },
        life: Math.random() * 100,
        maxLife: 100 + Math.random() * 50,
      }));
    };

    const onPointerMove = (e) => {
      const x = e.clientX;
      const y = e.clientY;
      mouse.vx = x - mouse.px;
      mouse.vy = y - mouse.py;
      mouse.px = mouse.x;
      mouse.py = mouse.y;
      mouse.x = x;
      mouse.y = y;
      mouse.active = true;
      mouse.strength = Math.min(1, mouse.strength + 0.18);
    };

    const onPointerLeave = () => {
      mouse.active = false;
    };

    const animate = () => {
      const w = window.innerWidth;
      const h = window.innerHeight;

      // Fade suave do rastro
      ctx.globalCompositeOperation = "destination-out";
      ctx.fillStyle = "rgba(0, 0, 0, 0.06)";
      ctx.fillRect(0, 0, w, h);
      ctx.globalCompositeOperation = "source-over";

      if (!mouse.active) {
        mouse.strength *= 0.92;
        mouse.vx *= 0.9;
        mouse.vy *= 0.9;
      } else {
        mouse.strength = Math.min(1, mouse.strength * 0.98 + 0.02);
        mouse.vx *= 0.86;
        mouse.vy *= 0.86;
      }

      const radius = mouseRadius;
      const radiusSq = radius * radius;
      const forceScale = mouseForce * mouse.strength;
      const speed = Math.hypot(mouse.vx, mouse.vy);
      const wakeBoost = Math.min(1.8, 0.35 + speed * 0.08);

      const t = Date.now() * 0.00008;
      for (const particle of particles) {
        particle.life += 1;
        if (particle.life > particle.maxLife) {
          particle.life = 0;
          particle.x = Math.random() * w;
          particle.y = Math.random() * h;
        }

        let opacity =
          Math.sin((particle.life / particle.maxLife) * Math.PI) * 0.42;

        const n = noise.simplex3(
          particle.x * noiseIntensity,
          particle.y * noiseIntensity,
          t
        );
        const angle = n * Math.PI * 4;
        let vx = Math.cos(angle) * 1.2;
        let vy = Math.sin(angle) * 1.2;

        // Interação com o mouse: afasta + arrasta no sentido do movimento
        if (mouse.strength > 0.02) {
          const dx = particle.x - mouse.x;
          const dy = particle.y - mouse.y;
          const distSq = dx * dx + dy * dy;
          if (distSq < radiusSq && distSq > 0.01) {
            const dist = Math.sqrt(distSq);
            const falloff = 1 - dist / radius;
            const f = falloff * falloff * forceScale * wakeBoost;
            const inv = 1 / dist;
            // Repulsão radial
            vx += dx * inv * f;
            vy += dy * inv * f;
            // Rastro no sentido do cursor
            vx += mouse.vx * MOUSE_WAKE * falloff;
            vy += mouse.vy * MOUSE_WAKE * falloff;
            opacity = Math.min(0.85, opacity + falloff * 0.35 * mouse.strength);
          }
        }

        particle.velocity.x = vx;
        particle.velocity.y = vy;
        particle.x += vx;
        particle.y += vy;

        if (particle.x < 0) particle.x = w;
        if (particle.x > w) particle.x = 0;
        if (particle.y < 0) particle.y = h;
        if (particle.y > h) particle.y = 0;

        const gold = particle.size > 1.05;
        ctx.fillStyle = gold
          ? `rgba(225, 185, 113, ${opacity * 0.7})`
          : `rgba(255, 255, 255, ${opacity})`;
        ctx.beginPath();
        ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
        ctx.fill();
      }

      requestAnimationFrame(animate);
    };

    resize();
    ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
    animate();

    window.addEventListener("resize", resize, { passive: true });
    // No document: canvas tem pointer-events:none para não bloquear a UI
    document.addEventListener("pointermove", onPointerMove, { passive: true });
    document.addEventListener("pointerleave", onPointerLeave, { passive: true });
    window.addEventListener("blur", onPointerLeave, { passive: true });
  }

  window.OptoFluidBackground = { init: initFluidBackground };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => initFluidBackground());
  } else {
    initFluidBackground();
  }
})();

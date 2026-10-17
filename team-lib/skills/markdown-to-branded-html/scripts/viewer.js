(function () {
  var STEPS = [0.15, 0.25, 0.4, 0.55, 0.75, 1, 1.4, 2, 3, 4, 6];
  var viewer = document.createElement('div');
  viewer.className = 'viewer';
  viewer.hidden = true;
  viewer.innerHTML =
    '<div class="viewer-bar">' +
      '<span class="vtitle"></span>' +
      '<button type="button" class="zbtn" data-a="out" aria-label="Zoom out">−</button>' +
      '<span class="zlevel"></span>' +
      '<button type="button" class="zbtn" data-a="in" aria-label="Zoom in">+</button>' +
      '<button type="button" class="zbtn" data-a="fit">Fit</button>' +
      '<button type="button" class="zbtn" data-a="full">100%</button>' +
      '<button type="button" class="zbtn close" data-a="close">Close ✕</button>' +
    '</div>' +
    '<div class="viewer-stage"><div class="pan"></div></div>' +
    '<div class="viewer-hint">Drag to move it around · scroll or pinch to zoom · double-click to zoom in · Esc to close</div>';
  document.body.appendChild(viewer);
  var stage = viewer.querySelector('.viewer-stage');
  var pan = viewer.querySelector('.pan');
  var vtitle = viewer.querySelector('.vtitle');
  var zlevel = viewer.querySelector('.zlevel');
  var svg = null, home = null, homeMax = '', natW = 0, natH = 0, z = 1, tx = 0, ty = 0;
  function draw() {
    pan.style.transform = 'translate(' + tx + 'px,' + ty + 'px) scale(' + z + ')';
    zlevel.textContent = Math.round(z * 100) + '%';
  }
  function fit() {
    var w = stage.clientWidth - 32, h = stage.clientHeight - 32;
    z = Math.min(w / natW, h / natH);
    if (!isFinite(z) || z <= 0) z = 1;
    tx = (stage.clientWidth - natW * z) / 2;
    ty = (stage.clientHeight - natH * z) / 2;
    draw();
  }
  function zoomAt(next, cx, cy) {
    next = Math.max(0.05, Math.min(8, next));
    tx = cx - (cx - tx) * (next / z);
    ty = cy - (cy - ty) * (next / z);
    z = next; draw();
  }
  function stepZoom(dir) {
    var i = 0;
    while (i < STEPS.length && STEPS[i] <= z + 0.0001) i++;
    var next = dir > 0 ? STEPS[Math.min(i, STEPS.length - 1)] : STEPS[Math.max(0, i - 2)];
    zoomAt(next, stage.clientWidth / 2, stage.clientHeight / 2);
  }
  function open(canvas) {
    svg = canvas.querySelector('svg');
    if (!svg) return;
    var vb = (svg.getAttribute('viewBox') || '').split(/[\s,]+/).map(Number);
    if (vb.length !== 4 || !(vb[2] > 0) || !(vb[3] > 0)) return;
    natW = vb[2]; natH = vb[3];
    home = canvas;
    var fig = canvas.closest('figure.dia');
    var cap = fig.querySelector('figcaption .nm');
    vtitle.textContent = cap ? cap.textContent : (fig.getAttribute('data-title') || '');
    pan.style.width = natW + 'px';
    homeMax = svg.style.maxWidth; svg.style.maxWidth = 'none';   // the page caps a figure; the viewer must not
    pan.appendChild(svg);
    viewer.hidden = false;
    document.body.classList.add('viewing');
    requestAnimationFrame(fit);
  }
  function close() {
    if (!svg) return;
    svg.style.width = '100%';
    svg.style.maxWidth = homeMax;
    home.insertBefore(svg, home.firstChild);
    svg = null; home = null;
    viewer.hidden = true;
    document.body.classList.remove('viewing');
  }
  viewer.addEventListener('click', function (e) {
    var b = e.target.closest('.zbtn'); if (!b) return;
    var a = b.getAttribute('data-a');
    if (a === 'in') stepZoom(1); else if (a === 'out') stepZoom(-1);
    else if (a === 'fit') fit(); else if (a === 'full') zoomAt(1, stage.clientWidth / 2, stage.clientHeight / 2);
    else if (a === 'close') close();
  });
  // pointer pan + two-finger pinch
  var pts = {}, lastDist = 0, px = 0, py = 0;
  stage.addEventListener('pointerdown', function (e) {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    pts[e.pointerId] = { x: e.clientX, y: e.clientY };
    px = e.clientX; py = e.clientY; lastDist = 0;
    stage.classList.add('grabbing'); stage.setPointerCapture(e.pointerId); e.preventDefault();
  });
  stage.addEventListener('pointermove', function (e) {
    if (!pts[e.pointerId]) return;
    pts[e.pointerId] = { x: e.clientX, y: e.clientY };
    var ids = Object.keys(pts);
    if (ids.length >= 2) {
      var a = pts[ids[0]], b = pts[ids[1]];
      var d = Math.hypot(a.x - b.x, a.y - b.y);
      var r = stage.getBoundingClientRect();
      if (lastDist) zoomAt(z * (d / lastDist), (a.x + b.x) / 2 - r.left, (a.y + b.y) / 2 - r.top);
      lastDist = d;
      return;
    }
    tx += e.clientX - px; ty += e.clientY - py; px = e.clientX; py = e.clientY; draw();
  });
  ['pointerup', 'pointercancel', 'pointerleave'].forEach(function (ev) {
    stage.addEventListener(ev, function (e) {
      delete pts[e.pointerId]; lastDist = 0;
      var ids = Object.keys(pts);
      if (ids.length) { px = pts[ids[0]].x; py = pts[ids[0]].y; } else stage.classList.remove('grabbing');
    });
  });
  stage.addEventListener('wheel', function (e) {
    e.preventDefault();
    var r = stage.getBoundingClientRect();
    zoomAt(z * (e.deltaY < 0 ? 1.15 : 1 / 1.15), e.clientX - r.left, e.clientY - r.top);
  }, { passive: false });
  stage.addEventListener('dblclick', function (e) {
    var r = stage.getBoundingClientRect();
    zoomAt(z * 1.6, e.clientX - r.left, e.clientY - r.top);
  });
  document.addEventListener('keydown', function (e) {
    if (viewer.hidden) return;
    if (e.key === 'Escape') close();
    else if (e.key === '+' || e.key === '=') stepZoom(1);
    else if (e.key === '-') stepZoom(-1);
    else if (e.key === '0') fit();
  });
  window.addEventListener('resize', function () { if (!viewer.hidden) fit(); });
  document.querySelectorAll('.canvas').forEach(function (canvas) {
    var tap = document.createElement('span');
    tap.className = 'tap';
    tap.textContent = 'Click to open · zoom and pan';
    canvas.appendChild(tap);
    canvas.addEventListener('click', function () { open(canvas); });
  });
})();

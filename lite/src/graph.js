const NS = 'http://www.w3.org/2000/svg';
const WIDTH = 152;
const HEIGHT = 104;
const COLORS = { fuel: '#f0b267', ox: '#62d6db', gas: '#b4bfcb', mechanical: '#c2a2ed' };
const TYPE_NAMES = { source: 'VERSORGUNG', line: 'LEITUNG', valve: 'VENTIL', injector: 'INJEKTOR', chamber: 'BRENNKAMMER', nozzle: 'DÜSE', sensor: 'MESSSTELLE', pump: 'PUMPE', regen: 'KÜHLKANAL', shaft: 'WELLE', gasSource: 'GASVERSORGUNG', turbine: 'TURBINE', exhaust: 'ABGASAUSLASS' };

export function fluidPortsFor(type) {
  return { input: !['source', 'gasSource', 'shaft'].includes(type), output: !['nozzle', 'exhaust', 'shaft'].includes(type) };
}

export function mechanicalLinks(nodes) {
  const shafts = new Map(nodes.filter(node => node.type === 'shaft').map(node => [node.id, node]));
  return nodes.filter(node => ['pump', 'turbine'].includes(node.type) && shafts.has(node.params?.shaftId))
    .map(node => ({ component: node, shaft: shafts.get(node.params.shaftId) }));
}

function svg(tag, attrs = {}, text) {
  const element = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, String(value));
  if (text !== undefined) element.textContent = text;
  return element;
}

export function nodeBounds(nodes) {
  if (!nodes.length) return { x: 0, y: 0, width: 640, height: 400 };
  const x = Math.min(...nodes.map(n => n.x));
  const y = Math.min(...nodes.map(n => n.y));
  return { x, y, width: Math.max(...nodes.map(n => n.x + WIDTH)) - x, height: Math.max(...nodes.map(n => n.y + HEIGHT)) - y };
}

export function connectionPath(a, b) {
  const bend = Math.max(48, Math.abs(b.x - a.x) * .46);
  return `M ${a.x} ${a.y} C ${a.x + bend} ${a.y}, ${b.x - bend} ${b.y}, ${b.x} ${b.y}`;
}

function formatNumber(value, digits = 1) {
  return Number.isFinite(value) ? new Intl.NumberFormat('de-DE', { maximumFractionDigits: digits }).format(value) : '—';
}

export class GraphEditor {
  constructor(container, callbacks = {}) {
    this.container = container;
    this.callbacks = callbacks;
    this.project = { nodes: [], edges: [] };
    this.options = { section: null };
    this.view = { x: -50, y: -50, width: 1000, height: 600 };
    this.pendingFrom = null;
    this.selectedEdge = null;
    this.pointers = new Map();
    this.initialized = false;
    this.abort = new AbortController();
    this.root = document.createElement('div');
    this.root.className = 'graph-root';
    this.root.style.cssText = 'position:relative;width:100%;height:100%;min-height:280px;overflow:hidden;background:#10181d';
    this.svg = svg('svg', { class: 'graph-svg', width: '100%', height: '100%', role: 'group', 'aria-label': 'Triebwerkssystem. Bauteile auswählen, verschieben und über Anschlüsse verbinden.', tabindex: '0' });
    this.svg.style.cssText = 'display:block;touch-action:none;user-select:none;outline-offset:-3px';
    this.svg.append(svg('style', {}, `
      .graph-node{cursor:grab;outline:none}.graph-node:active{cursor:grabbing}
      .graph-node .graph-node-body{transition:fill .12s,stroke .12s}
      .graph-node:hover .graph-node-body{fill:#202d35;stroke:#627784}
      .graph-node:focus-visible .graph-node-body{stroke:#fff;stroke-width:3}
      .graph-port{cursor:crosshair;outline:none}.graph-port:hover .graph-port-dot,.graph-port:focus-visible .graph-port-dot{r:7;stroke:#fff;stroke-width:2}
      .graph-section-link{cursor:pointer;outline:none}.graph-section-link:hover text,.graph-section-link:focus-visible text{fill:#fff}
      .graph-edge-hit{cursor:pointer}.graph-delete{cursor:pointer;outline:none}.graph-delete:hover circle,.graph-delete:focus-visible circle{fill:#9c4646}
      .graph-svg text{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;pointer-events:none}
      .graph-svg .graph-mono{font-family:ui-monospace,'Cascadia Code',Consolas,monospace}
      @media(prefers-reduced-motion:reduce){.graph-node .graph-node-body{transition:none}}
    `));
    const defs = svg('defs');
    const pattern = svg('pattern', { id: 'graph-dots', width: 24, height: 24, patternUnits: 'userSpaceOnUse' });
    pattern.append(svg('circle', { cx: 1, cy: 1, r: .8, fill: '#29353c' }));
    defs.append(pattern);
    this.svg.append(defs);
    this.bg = svg('rect', { fill: 'url(#graph-dots)', class: 'graph-background' });
    this.scene = svg('g', { class: 'graph-scene' });
    this.svg.append(this.bg, this.scene);
    this.controls = document.createElement('div');
    this.controls.className = 'graph-controls';
    this.controls.style.cssText = 'position:absolute;left:16px;bottom:16px;display:flex;gap:4px;padding:4px;border:1px solid #34434c;background:#172128;border-radius:8px;box-shadow:0 4px 18px #0003';
    for (const [label, text, action] of [['Vergrößern', '+', () => this.zoom(.8)], ['Verkleinern', '−', () => this.zoom(1.25)], ['Gesamtes System einpassen', '⌖', () => this.fit()]]) {
      const button = document.createElement('button');
      button.type = 'button'; button.textContent = text; button.title = label; button.setAttribute('aria-label', label);
      button.style.cssText = 'width:40px;height:40px;border:0;border-radius:5px;background:transparent;color:#dce6eb;font-size:22px;cursor:pointer';
      button.addEventListener('click', action, { signal: this.abort.signal });
      this.controls.append(button);
    }
    this.hint = document.createElement('div');
    this.hint.className = 'graph-hint';
    this.hint.setAttribute('role', 'status');
    this.hint.style.cssText = 'position:absolute;left:16px;top:14px;max-width:calc(100% - 32px);color:#aabcc7;font:11px/1.5 system-ui;pointer-events:none;background:#10181ddd;padding:6px 9px;border-radius:5px';
    this.root.append(this.svg, this.controls, this.hint);
    container.append(this.root);
    this.listen('pointerdown', e => this.pointerDown(e));
    this.listen('pointermove', e => this.pointerMove(e));
    this.listen('pointerup', e => this.pointerUp(e));
    this.listen('pointercancel', e => this.pointerUp(e, true));
    this.listen('wheel', e => { e.preventDefault(); this.zoom(Math.exp(Math.max(-1, Math.min(1, e.deltaY / 500))), this.point(e)); }, { passive: false });
    this.listen('keydown', e => this.keyDown(e));
    this.listen('dblclick', e => { const target = e.target.closest('[data-section]'); if (target) this.callbacks.onSection?.(target.dataset.section); });
    this.resizeObserver = new ResizeObserver(() => {
      if (!this.root.clientWidth || !this.root.clientHeight) return;
      if (!this.initialized && this.project.nodes.length) this.fit();
      else {
        const centerX = this.view.x + this.view.width / 2;
        this.view.width = this.view.height * this.aspect();
        this.view.x = centerX - this.view.width / 2;
        this.applyView();
      }
    });
    this.resizeObserver.observe(this.root);
  }

  listen(type, fn, extra = {}) { this.svg.addEventListener(type, fn, { ...extra, signal: this.abort.signal }); }
  aspect() { return Math.max(.25, this.root.clientWidth / Math.max(1, this.root.clientHeight)); }
  visibleNodes() { return this.project.nodes.filter(n => !this.options.section || n.section === this.options.section); }
  point(event) {
    const rect = this.svg.getBoundingClientRect();
    return { x: this.view.x + (event.clientX - rect.left) / rect.width * this.view.width, y: this.view.y + (event.clientY - rect.top) / rect.height * this.view.height };
  }
  applyView() {
    const { x, y, width, height } = this.view;
    this.svg.setAttribute('viewBox', `${x} ${y} ${width} ${height}`);
    for (const [key, value] of Object.entries({ x, y, width, height })) this.bg.setAttribute(key, value);
  }
  fit() {
    if (!this.root.clientWidth || !this.root.clientHeight) return;
    const bounds = nodeBounds(this.visibleNodes());
    const padding = this.options.section ? 150 : 90;
    const aspect = this.aspect();
    const width = Math.max(bounds.width + padding * 2, (bounds.height + 170) * aspect);
    const height = width / aspect;
    this.view = { x: bounds.x + bounds.width / 2 - width / 2, y: bounds.y + bounds.height / 2 - height / 2, width, height };
    this.initialized = true;
    this.applyView();
  }
  zoom(factor, anchor) {
    anchor ||= { x: this.view.x + this.view.width / 2, y: this.view.y + this.view.height / 2 };
    const width = Math.max(220, Math.min(6000, this.view.width * factor));
    factor = width / this.view.width;
    this.view = { x: anchor.x + (this.view.x - anchor.x) * factor, y: anchor.y + (this.view.y - anchor.y) * factor, width, height: this.view.height * factor };
    this.applyView();
  }
  update(project, options = {}) {
    const sectionChanged = this.options.section !== options.section;
    this.project = project;
    this.options = options;
    if (!project.nodes.some(n => n.id === this.pendingFrom)) this.pendingFrom = null;
    if (!project.edges.some(e => e.id === this.selectedEdge)) this.selectedEdge = null;
    if (sectionChanged) { this.pendingFrom = null; this.selectedEdge = null; }
    this.render();
    if (!this.initialized || sectionChanged) this.fit();
  }
  position(node) {
    return this.drag?.kind === 'node' && this.drag.id === node.id && this.drag.moved ? this.drag.current : node;
  }
  port(node, output, otherMedium) {
    const p = this.position(node);
    return { x: p.x + (output ? WIDTH : 0), y: p.y + HEIGHT / 2 + (node.type === 'injector' && !output ? (otherMedium === 'ox' ? -15 : 15) : 0) };
  }
  render() {
    const active = document.activeElement;
    const focusData = active && this.scene.contains(active) ? { ...active.dataset } : null;
    this.scene.replaceChildren();
    const nodes = this.visibleNodes();
    const ids = new Set(nodes.map(n => n.id));
    const nodeMap = new Map(this.project.nodes.map(n => [n.id, n]));
    this.hint.textContent = this.pendingFrom ? 'Ausgang gewählt · Zielanschluss antippen · Esc zum Abbrechen' : this.selectedEdge ? 'Verbindung gewählt · × oder Entf zum Entfernen' : 'Bauteil auswählen · Anschlüsse verbinden · Hintergrund verschieben';
    if (!this.options.section) {
      for (const section of ['ox', 'fuel']) {
        const sectionNodes = nodes.filter(n => n.section === section).map(n => this.position(n));
        if (!sectionNodes.length) continue;
        const b = nodeBounds(sectionNodes);
        const group = svg('g', { 'data-section': section });
        group.append(svg('rect', { x: b.x - 24, y: b.y - 48, width: b.width + 48, height: b.height + 72, rx: 12, fill: COLORS[section], 'fill-opacity': .025, stroke: COLORS[section], 'stroke-opacity': .23, 'stroke-dasharray': '5 5' }));
        const link = svg('g', { class: 'graph-section-link', role: 'button', tabindex: 0, 'aria-label': `${section === 'ox' ? 'Oxidator' : 'Brennstoff'}-Section öffnen`, 'data-section-open': section });
        link.append(svg('rect', { x: b.x - 10, y: b.y - 46, width: 190, height: 36, rx: 4, fill: '#10181d' }));
        link.append(svg('text', { x: b.x, y: b.y - 24, fill: COLORS[section], 'font-size': 10, 'font-weight': 600, 'letter-spacing': '1.1' }, section === 'ox' ? 'OXIDATOR · SECTION ↗' : 'BRENNSTOFF · SECTION ↗'));
        group.append(link); this.scene.append(group);
      }
    }
    for (const { component, shaft } of mechanicalLinks(this.project.nodes)) {
      const componentVisible = ids.has(component.id), shaftVisible = ids.has(shaft.id);
      if (!componentVisible && !shaftVisible) continue;
      const c = this.position(component), s = this.position(shaft);
      let a = { x: c.x + WIDTH / 2, y: c.y + HEIGHT };
      let b = { x: s.x + WIDTH / 2, y: s.y + HEIGHT };
      if (!shaftVisible) b = { x: a.x + 90, y: a.y + 68 };
      if (!componentVisible) a = { x: b.x - 90, y: b.y + 68 };
      const bendY = Math.max(a.y, b.y) + 50;
      const link = svg('g', { class: 'graph-mechanical-link', role: 'img', 'aria-label': `Mechanische Kopplung: ${component.label} mit ${shaft.label}`, 'pointer-events': 'none' });
      link.append(svg('title', {}, `Wellenkopplung · ${component.label} → ${shaft.label} · im Inspector zuordnen`));
      link.append(svg('path', { d: `M ${a.x} ${a.y} C ${a.x} ${bendY}, ${b.x} ${bendY}, ${b.x} ${b.y}`, fill: 'none', stroke: COLORS.mechanical, 'stroke-width': 1.6, 'stroke-dasharray': '7 5', 'stroke-opacity': .75 }));
      for (const point of [a, b]) link.append(svg('circle', { cx: point.x, cy: point.y, r: 3.5, fill: '#10181d', stroke: COLORS.mechanical, 'stroke-width': 1.5 }));
      if (!shaftVisible || !componentVisible) link.append(svg('text', { x: !shaftVisible ? b.x : a.x, y: (!shaftVisible ? b.y : a.y) + 18, 'text-anchor': 'middle', fill: COLORS.mechanical, 'font-size': 9 }, (!shaftVisible ? shaft.label : component.label).slice(0, 22)));
      this.scene.append(link);
    }
    for (const edge of this.project.edges) {
      const from = nodeMap.get(edge.from), to = nodeMap.get(edge.to);
      if (!from || !to) continue;
      const fromVisible = ids.has(from.id), toVisible = ids.has(to.id);
      if (!fromVisible && !toVisible) continue;
      let a = this.port(from, true), b = this.port(to, false, from.medium);
      let boundary = null;
      if (!fromVisible) { a = { x: b.x - 100, y: b.y }; boundary = { node: from, p: a, input: true }; }
      if (!toVisible) { b = { x: a.x + 100, y: a.y }; boundary = { node: to, p: b, input: false }; }
      const color = COLORS[from.medium] || COLORS.gas;
      const path = connectionPath(a, b);
      this.scene.append(svg('path', { d: path, fill: 'none', stroke: this.selectedEdge === edge.id ? '#fff' : color, 'stroke-width': this.selectedEdge === edge.id ? 3 : 2, 'stroke-opacity': this.options.stale ? .5 : .8 }));
      this.scene.append(svg('path', { d: path, fill: 'none', stroke: 'transparent', 'stroke-width': 18, class: 'graph-edge-hit', 'data-edge': edge.id, role: 'button', tabindex: 0, 'aria-label': `Verbindung ${from.label} nach ${to.label} auswählen` }));
      const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
      this.scene.append(svg('path', { d: `M ${mx - 3} ${my - 4} L ${mx + 3} ${my} L ${mx - 3} ${my + 4}`, fill: 'none', stroke: color, 'stroke-width': 1.5 }));
      if (this.selectedEdge === edge.id) {
        const del = svg('g', { class: 'graph-delete', 'data-delete-edge': edge.id, tabindex: 0, role: 'button', 'aria-label': 'Ausgewählte Verbindung löschen' });
        del.append(svg('circle', { cx: mx, cy: my - 22, r: 15, fill: '#63373b', stroke: '#c97b7b' }), svg('path', { d: `M ${mx-4} ${my-26} l 8 8 m -8 0 l 8 -8`, stroke: '#fff', 'stroke-width': 1.5 }));
        this.scene.append(del);
      }
      if (boundary) {
        const p = boundary.p;
        this.scene.append(svg('circle', { cx: p.x, cy: p.y, r: 4, fill: color }), svg('text', { x: p.x, y: p.y - 14, 'text-anchor': boundary.input ? 'start' : 'end', fill: '#8fa4b2', 'font-size': 10 }, boundary.node.label.slice(0, 22)));
      }
    }
    for (const node of nodes) this.renderNode(node);
    if (!nodes.length) {
      this.scene.append(svg('text', { x: 320, y: 200, 'text-anchor': 'middle', fill: '#91a5b2', 'font-size': 15 }, 'Komponenten aus der Bibliothek hinzufügen'));
    }
    if (focusData) {
      const keys = Object.keys(focusData);
      if (keys.length) {
        const match = [...this.scene.querySelectorAll('[tabindex]')].find(el => keys.every(key => el.dataset[key] === focusData[key]));
        match?.focus({ preventScroll: true });
      }
    }
  }
  renderNode(node) {
    const pos = this.position(node), color = COLORS[node.medium] || COLORS.gas;
    const selected = this.options.selectedId === node.id;
    const hasError = this.options.result?.errors?.some(e => e.nodeId === node.id);
    const group = svg('g', { transform: `translate(${pos.x} ${pos.y})`, class: 'graph-node', 'data-node': node.id, tabindex: 0, role: 'button', 'aria-label': `${node.label}, ${TYPE_NAMES[node.type] || node.type}. Enter zum Auswählen, Pfeiltasten zum Verschieben.`, 'aria-pressed': selected });
    group.append(svg('rect', { x: 0, y: 0, width: WIDTH, height: HEIGHT, rx: 8, fill: selected ? '#25343b' : '#19242b', stroke: hasError ? '#ec8e8e' : selected ? color : '#3a4a54', 'stroke-width': selected ? 2 : 1, class: 'graph-node-body' }));
    group.append(svg('rect', { x: 0, y: 24, width: 2, height: 34, rx: 1, fill: color }));
    const symbol = svg('g', { transform: 'translate(15 13)', stroke: color, fill: 'none', 'stroke-width': 1.5, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'pointer-events': 'none' });
    this.drawSymbol(symbol, node);
    group.append(symbol);
    group.append(svg('text', { x: WIDTH - 12, y: 24, 'text-anchor': 'end', fill: '#8298a5', 'font-size': 8.2, 'letter-spacing': '.7', class: 'graph-mono' }, TYPE_NAMES[node.type] || node.type));
    group.append(svg('text', { x: 14, y: 63, fill: '#e8f0f4', 'font-size': 12, 'font-weight': 550 }, node.label.length > 21 ? `${node.label.slice(0, 20)}…` : node.label));
    const title = svg('title', {}, node.label); group.append(title);
    group.append(svg('text', { x: 14, y: 84, fill: this.options.stale ? '#82949f' : '#afbec8', 'font-size': 10, class: 'graph-mono' }, this.nodeDetail(node)));
    const fluidPorts = fluidPortsFor(node.type);
    if (fluidPorts.input) {
      if (node.type === 'injector') {
        group.append(this.makePort(node, false, 37, 'ox'), this.makePort(node, false, 67, 'fuel'));
      } else group.append(this.makePort(node, false, HEIGHT / 2));
    }
    if (fluidPorts.output) group.append(this.makePort(node, true, HEIGHT / 2));
    this.scene.append(group);
  }
  makePort(node, output, y, medium) {
    const x = output ? WIDTH : 0;
    const selected = output && this.pendingFrom === node.id;
    const color = COLORS[medium || node.medium] || COLORS.gas;
    const port = svg('g', { class: 'graph-port', 'data-port-node': node.id, 'data-port-output': output ? '1' : '0', tabindex: 0, role: 'button', 'aria-label': `${node.label}: ${output ? 'Ausgang wählen' : 'Eingang verbinden'}${medium ? ` (${medium === 'ox' ? 'Oxidator' : 'Brennstoff'})` : ''}` });
    port.append(svg('circle', { cx: x, cy: y, r: 14, fill: 'transparent' }), svg('circle', { cx: x, cy: y, r: selected ? 7 : 4, fill: selected ? '#fff' : '#17232b', stroke: color, 'stroke-width': 2, class: 'graph-port-dot' }));
    return port;
  }
  nodeDetail(node) {
    const station = this.options.result?.stations?.[node.id];
    if (station && !this.options.stale) return `${node.medium === 'gas' ? 'p_mod' : 'p_req'} ${formatNumber(station.pressureBar)} bar`;
    const p = node.params || {};
    if (node.type === 'source' || node.type === 'gasSource') return `${formatNumber(p.pressureBar)} bar · ${formatNumber(p.temperatureK)} K`;
    if (node.type === 'line') return `Ø ${formatNumber(p.diameterMm)} mm · ${formatNumber(p.lengthM)} m`;
    if (node.type === 'valve') return p.open === false ? 'Geschlossen' : `Offen · K ${formatNumber(p.k)}`;
    if (node.type === 'chamber') return `${formatNumber(this.project.design?.pcBar)} bar · O/F ${formatNumber(this.project.design?.of, 2)}`;
    if (node.type === 'nozzle') return `Glocke · ε ${formatNumber(this.project.design?.eps)}`;
    if (node.type === 'injector') return 'LOX + RP-1';
    if (node.type === 'sensor') return ({ pressure: 'Druckmessstelle', temperature: 'Temperaturmessstelle', massflow: 'Massenstrommessstelle' })[p.quantity] || 'Virtuelle Messstelle';
    if (node.type === 'pump') return `Δp +${formatNumber(p.riseBar)} bar`;
    if (node.type === 'regen') return `Q ${formatNumber(p.heatKW)} kW`;
    if (node.type === 'shaft') return `${formatNumber(p.rpm, 0)} min⁻¹`;
    if (node.type === 'turbine') return `p_out ${formatNumber(p.outletBar)} bar`;
    if (node.type === 'exhaust') return `p_exit ${formatNumber(p.exitBar)} bar`;
    return 'Vorentwurf';
  }
  drawSymbol(g, node) {
    const append = (tag, attrs) => g.append(svg(tag, attrs));
    switch (node.type) {
      case 'source':
        append('rect', { x: 5, y: 1, width: 25, height: 30, rx: 10 });
        append('path', { d: 'M 5 12 Q 17 18 30 12 M 30 19 H 38 M 10 34 H 25' }); break;
      case 'line':
        append('path', { d: 'M 0 12 H 36 M 0 22 H 36 M 6 8 V 26 M 30 8 V 26' }); break;
      case 'valve':
        append('path', { d: 'M 0 17 H 5 L 29 28 V 6 L 5 28 V 6 L 29 17 H 37 M 17 17 V 1 M 11 1 H 23' });
        if (node.params?.open === false) append('path', { d: 'M 0 32 L 35 0', stroke: '#ee8f86', 'stroke-width': 2 }); break;
      case 'injector':
        append('path', { d: 'M 0 8 H 12 M 0 25 H 12 M 12 1 V 32 H 21 V 1 Z M 25 6 L 36 3 M 25 12 H 37 M 25 20 H 37 M 25 26 L 36 30' }); break;
      case 'chamber':
        append('path', { d: 'M 2 3 H 23 Q 35 3 35 15 V 20 Q 35 32 23 32 H 2 Z M 35 14 H 40 M 35 21 H 40' });
        append('path', { d: 'M 12 24 C 5 17 15 17 14 9 C 25 16 25 22 20 25', 'stroke-opacity': .65 }); break;
      case 'nozzle':
        append('path', { d: 'M 0 7 C 8 7 9 12 13 12 C 20 12 24 4 38 0 M 0 26 C 8 26 9 21 13 21 C 20 21 24 29 38 33 M 0 7 V 26 M 38 0 V 33' }); break;
      case 'sensor':
        append('circle', { cx: 18, cy: 15, r: 12 });
        append('path', { d: 'M 18 27 V 34 M 12 34 H 24 M 18 15 L 24 9' }); break;
      case 'pump':
        append('circle', { cx: 18, cy: 17, r: 13 });
        append('path', { d: 'M 0 17 H 5 M 31 17 H 39 M 13 8 L 25 17 L 13 26 Z M 18 30 V 36' }); break;
      case 'regen':
        append('rect', { x: 4, y: 4, width: 29, height: 27, rx: 3 });
        append('path', { d: 'M 0 17 H 9 V 10 H 15 V 25 H 21 V 10 H 27 V 17 H 39 M 12 0 V -4 M 25 0 V -4' }); break;
      case 'shaft':
        append('path', { d: 'M 0 14 H 38 V 20 H 0 Z M 7 8 V 26 M 11 8 V 26 M 27 8 V 26 M 31 8 V 26 M 12 3 Q 19 -2 25 3 M 22 0 L 25 3 L 22 5' }); break;
      case 'gasSource':
        append('rect', { x: 4, y: 1, width: 25, height: 30, rx: 8 });
        append('path', { d: 'M 29 17 H 39 M 18 6 L 12 17 H 21 L 15 26' }); break;
      case 'turbine':
        append('circle', { cx: 18, cy: 17, r: 13 });
        append('circle', { cx: 18, cy: 17, r: 3 });
        append('path', { d: 'M 0 17 H 5 M 31 17 H 39 M 18 14 Q 10 7 17 4 M 21 17 Q 28 9 31 17 M 18 20 Q 26 27 19 30 M 15 17 Q 8 25 5 17 M 18 30 V 36' }); break;
      case 'exhaust':
        append('path', { d: 'M 0 11 H 12 L 30 3 M 0 23 H 12 L 30 31 M 20 17 H 39 M 34 12 L 39 17 L 34 22' }); break;
    }
  }
  activate(target) {
    const port = target.closest('[data-port-node]');
    if (port) {
      if (port.dataset.portOutput === '1') this.pendingFrom = this.pendingFrom === port.dataset.portNode ? null : port.dataset.portNode;
      else if (this.pendingFrom && this.pendingFrom !== port.dataset.portNode) {
        const from = this.pendingFrom; this.pendingFrom = null;
        this.callbacks.onConnect?.(from, port.dataset.portNode);
      } else this.hint.textContent = 'Zuerst den Ausgang eines Bauteils wählen.';
      this.render(); return true;
    }
    const del = target.closest('[data-delete-edge]');
    if (del) { const id = del.dataset.deleteEdge; this.selectedEdge = null; this.callbacks.onDeleteEdge?.(id); this.render(); return true; }
    const edge = target.closest('[data-edge]');
    if (edge) { this.selectedEdge = edge.dataset.edge; this.render(); return true; }
    const section = target.closest('[data-section-open]');
    if (section) { this.callbacks.onSection?.(section.dataset.sectionOpen); return true; }
    return false;
  }
  pointerDown(event) {
    if (event.button !== 0) return;
    this.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    this.svg.setPointerCapture(event.pointerId);
    if (this.pointers.size === 2) {
      const [a,b] = [...this.pointers.values()];
      this.drag = null;
      this.pinch = { distance: Math.hypot(a.x-b.x,a.y-b.y) };
      return;
    }
    const target = event.target;
    if (target.closest('[data-port-node],[data-delete-edge],[data-edge],[data-section-open]')) {
      this.drag = { kind: 'action', target, sx: event.clientX, sy: event.clientY }; return;
    }
    const nodeElement = target.closest('[data-node]');
    const start = this.point(event);
    if (nodeElement) {
      const node = this.project.nodes.find(n => n.id === nodeElement.dataset.node);
      if (node) this.drag = { kind: 'node', id: node.id, start, original: { x: node.x, y: node.y }, current: { x: node.x, y: node.y }, moved: false, sx: event.clientX, sy: event.clientY };
    } else this.drag = { kind: 'pan', start, original: { ...this.view }, sx: event.clientX, sy: event.clientY, moved: false };
  }
  pointerMove(event) {
    if (!this.pointers.has(event.pointerId)) return;
    this.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (this.pinch && this.pointers.size === 2) {
      const [a,b] = [...this.pointers.values()];
      const distance = Math.max(1, Math.hypot(a.x-b.x,a.y-b.y));
      const anchor = this.point({ clientX: (a.x+b.x)/2, clientY: (a.y+b.y)/2 });
      this.zoom(this.pinch.distance / distance, anchor);
      this.pinch.distance = distance; return;
    }
    const drag = this.drag;
    if (!drag) return;
    const moved = Math.hypot(event.clientX-drag.sx,event.clientY-drag.sy) > 4;
    if (drag.kind === 'node' && moved) {
      const point = this.point(event);
      drag.moved = true;
      drag.current = { x: Math.round((drag.original.x + point.x - drag.start.x)/8)*8, y: Math.round((drag.original.y + point.y - drag.start.y)/8)*8 };
      this.render();
    } else if (drag.kind === 'pan') {
      drag.moved ||= moved;
      const rect = this.svg.getBoundingClientRect();
      this.view.x = drag.original.x - (event.clientX-drag.sx)/rect.width * this.view.width;
      this.view.y = drag.original.y - (event.clientY-drag.sy)/rect.height * this.view.height;
      this.applyView();
    }
  }
  pointerUp(event, cancelled = false) {
    this.pointers.delete(event.pointerId);
    if (this.pinch) { if (this.pointers.size < 2) this.pinch = null; this.drag = null; return; }
    const drag = this.drag; this.drag = null;
    if (!drag || cancelled) { this.render(); return; }
    if (drag.kind === 'node') {
      if (drag.moved) this.callbacks.onMove?.(drag.id, drag.current.x, drag.current.y);
      else this.callbacks.onSelect?.(drag.id);
      this.render();
    } else if (drag.kind === 'action' && Math.hypot(event.clientX-drag.sx,event.clientY-drag.sy) <= 5) this.activate(drag.target);
    else if (drag.kind === 'pan' && !drag.moved) { this.pendingFrom = null; this.selectedEdge = null; this.render(); }
  }
  keyDown(event) {
    if (event.key === 'Escape') { this.pendingFrom = null; this.selectedEdge = null; this.render(); return; }
    if ((event.key === 'Delete' || event.key === 'Backspace') && this.selectedEdge) {
      event.preventDefault(); event.stopPropagation(); const edge = this.selectedEdge; this.selectedEdge = null; this.callbacks.onDeleteEdge?.(edge); return;
    }
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault(); if (this.activate(event.target)) return;
      const node = event.target.closest('[data-node]');
      if (node) this.callbacks.onSelect?.(node.dataset.node);
    }
    const nodeElement = event.target.closest('[data-node]');
    if (nodeElement && ['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)) {
      event.preventDefault(); const node = this.project.nodes.find(n => n.id === nodeElement.dataset.node);
      const distance = event.shiftKey ? 40 : 8;
      if (node) this.callbacks.onMove?.(node.id, node.x + (event.key === 'ArrowLeft' ? -distance : event.key === 'ArrowRight' ? distance : 0), node.y + (event.key === 'ArrowUp' ? -distance : event.key === 'ArrowDown' ? distance : 0));
      this.scene.querySelectorAll('[data-node]').forEach(el => { if(el.dataset.node === node?.id) el.focus(); });
    }
  }
  destroy() { this.abort.abort(); this.resizeObserver.disconnect(); this.root.remove(); }
}

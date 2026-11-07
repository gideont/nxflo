/* Inspect the report's original chart using its published payback formula. */
(() => {
    const chart = document.getElementById('payback-chart');
    if (!chart) return;
    const tooltip = chart.querySelector('.payback-tooltip');
    const marker = chart.querySelector('.payback-marker');
    const costs = [1500, 3000, 6000];
    const colors = ['#ec278d', '#6035ed', '#0c2139'];
    // Coordinates in the original 1008 × 480 image, including its labels.
    const point = (hours, cost) => ({ x: 77.5 + 83.6 * hours, y: 401 - 9.725 * cost / (hours * 50) });
    let hours = 5;
    let series = 1;
    chart.tabIndex = 0;
    chart.setAttribute('role', 'group');
    chart.setAttribute('aria-label', 'Interactive automation payback chart');
    chart.setAttribute('aria-describedby', 'payback-chart-help');
    document.getElementById('payback-chart-help').hidden = false;

    const hide = () => { tooltip.hidden = true; marker.hidden = true; };
    const show = () => {
        const cost = costs[series];
        const weeks = cost / (hours * 50);
        const p = point(hours, cost);
        tooltip.replaceChildren();
        const title = document.createElement('strong');
        title.textContent = `Build cost $${cost.toLocaleString('en-US')}`;
        const detail = document.createElement('span');
        detail.textContent = `${hours.toFixed(1)} hours saved/week · ${weeks.toFixed(1)} weeks to pay back`;
        tooltip.append(title, detail);
        tooltip.style.borderLeftColor = colors[series];
        marker.style.background = colors[series];
        marker.style.left = `${p.x / 1008 * 100}%`;
        marker.style.top = `${p.y / 480 * 100}%`;
        tooltip.hidden = false;
        marker.hidden = false;
        const x = p.x / 1008 * chart.clientWidth;
        const y = p.y / 480 * chart.clientHeight;
        // Keep the box inside the chart even near its edges on narrow screens.
        tooltip.style.left = `${Math.max(0, Math.min(chart.clientWidth - tooltip.offsetWidth, x + 12))}px`;
        tooltip.style.top = `${Math.max(0, Math.min(chart.clientHeight - tooltip.offsetHeight, y - tooltip.offsetHeight - 12))}px`;
    };
    const inspect = (event) => {
        const rect = chart.getBoundingClientRect();
        const x = (event.clientX - rect.left) / rect.width * 1008;
        const y = (event.clientY - rect.top) / rect.height * 480;
        let best = Infinity;
        // Compare visible curve points so the nearest line is identified even
        // when its value at the pointer's x-coordinate lies above the plot.
        costs.forEach((cost, index) => {
            for (let step = 100; step <= 1000; step += 2) {
                const h = step / 100;
                if (cost / (h * 50) > 40) continue;
                const p = point(h, cost);
                const distance = (p.x - x) ** 2 + (p.y - y) ** 2;
                if (distance < best) { best = distance; hours = h; series = index; }
            }
        });
        show();
    };
    chart.addEventListener('pointermove', inspect);
    chart.addEventListener('pointerdown', inspect);
    chart.addEventListener('pointerleave', (event) => { if (event.pointerType === 'mouse') hide(); });
    chart.addEventListener('focus', show);
    chart.addEventListener('blur', hide);
    chart.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') { hide(); return; }
        if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
        event.preventDefault();
        if (event.key === 'ArrowUp') series = (series + 1) % costs.length;
        if (event.key === 'ArrowDown') series = (series + costs.length - 1) % costs.length;
        if (event.key === 'ArrowLeft') hours -= .5;
        if (event.key === 'ArrowRight') hours += .5;
        hours = Math.max(1, Math.min(10, hours));
        hours = Math.max(hours, costs[series] / (40 * 50));
        show();
    });
    document.addEventListener('pointerdown', (event) => { if (!chart.contains(event.target)) hide(); });
    window.addEventListener('resize', hide);
})();

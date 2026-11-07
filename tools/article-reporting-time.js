/* Published report estimates remain visible without JavaScript. */
(() => {
    const chart = document.getElementById('reporting-time-chart');
    if (!chart) return;
    const rows = [...chart.querySelectorAll('.reporting-time-row')];
    const tooltip = chart.querySelector('.reporting-time-tooltip');
    const hide = () => { tooltip.hidden = true; };
    const show = (row) => {
        tooltip.replaceChildren();
        for (const [tag, text, className] of [
            ['strong', row.dataset.source, ''],
            ['span', row.dataset.value, ''],
            ['span', row.dataset.detail, 'reporting-time-detail'],
        ]) {
            const node = document.createElement(tag);
            node.textContent = text;
            node.className = className;
            tooltip.append(node);
        }
        tooltip.style.borderLeftColor = getComputedStyle(row).getPropertyValue('--bar-color');
        tooltip.hidden = false;
        const top = row.offsetTop + row.offsetHeight + 6;
        tooltip.style.left = `${Math.max(0, chart.clientWidth - tooltip.offsetWidth)}px`;
        tooltip.style.top = `${Math.max(0, Math.min(chart.clientHeight - tooltip.offsetHeight, top))}px`;
    };
    rows.forEach((row, index) => {
        row.addEventListener('pointerenter', (event) => {
            if (event.pointerType === 'mouse') show(row);
        });
        row.addEventListener('pointerleave', (event) => {
            if (event.pointerType === 'mouse') hide();
        });
        row.addEventListener('focus', () => show(row));
        row.addEventListener('click', () => show(row));
        row.addEventListener('blur', hide);
        row.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') { hide(); return; }
            if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
            event.preventDefault();
            let next = index + (event.key === 'ArrowDown' ? 1 : -1);
            if (event.key === 'Home') next = 0;
            if (event.key === 'End') next = rows.length - 1;
            rows[(next + rows.length) % rows.length].focus();
        });
    });
    document.addEventListener('pointerdown', (event) => {
        if (!chart.contains(event.target)) hide();
    });
    window.addEventListener('resize', hide);
})();

/* Documents stay in memory in this tab. No uploads, analytics, or persistent storage. */
(() => {
    'use strict';
    const $ = id => document.getElementById(id);
    const count = $('page-count');
    const slots = $('page-slots');
    const status = $('tool-status');
    const filename = $('pdf-name');
    const controls = $('tool-controls');
    const maxFile = 20 * 1024 * 1024;
    const maxTotal = 100 * 1024 * 1024;
    let entries = [];
    let resultURL = null;
    let busy = false;
    let generation = 0;
    for (let n = 1; n <= 50; n++) count.add(new Option(String(n), String(n)));

    function invalidate() {
        if (resultURL) URL.revokeObjectURL(resultURL);
        resultURL = null;
        $('download-result').hidden = true;
        $('download-pdf').removeAttribute('href');
        status.textContent = '';
    }
    function update() {
        const ready = entries.filter(entry => entry.file).length;
        const loading = entries.some(entry => entry.loading);
        const pages = entries.reduce((sum, entry) => sum + (entry.pages || 0), 0);
        $('file-summary').textContent = `${ready} of ${entries.length} files ready · ${pages} output ${pages === 1 ? 'page' : 'pages'}`;
        $('combine').disabled = busy || loading || !entries.length || ready !== entries.length || !filename.value.trim() || pages > 200;
        if (pages > 200) status.textContent = 'Please reduce your files to 200 output pages or fewer.';
    }
    function clearEntry(entry) {
        entry.file = null;
        entry.pages = 0;
        entry.kind = null;
        entry.input.value = '';
        entry.card.classList.remove('is-ready');
        entry.remove.hidden = true;
    }
    async function choose(entry, files) {
        if (busy) return;
        const attempt = ++entry.attempt;
        const currentGeneration = generation;
        invalidate();
        clearEntry(entry);
        entry.loading = true;
        entry.details.textContent = 'Checking file…';
        update();
        try {
            if (files.length !== 1) throw new Error('Please choose just one file for this box.');
            const file = files[0];
            if (!file.size) throw new Error('This file is empty. Choose another file.');
            if (file.size > maxFile) throw new Error('This file exceeds 20 MB. Choose a smaller file.');
            if (entries.reduce((sum, item) => sum + (item.file?.size || 0), 0) + file.size > maxTotal) throw new Error('The files exceed 100 MB total. Choose smaller files.');
            if (!window.PDFLib) throw new Error('The PDF engine could not load. Refresh the page and try again.');
            const bytes = new Uint8Array(await file.arrayBuffer());
            const isPDF = /\.pdf$/i.test(file.name) && new TextDecoder().decode(bytes.slice(0, 1024)).includes('%PDF-');
            const isJPG = /\.jpe?g$/i.test(file.name) && bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255;
            let pages;
            if (isPDF) {
                const pdf = await PDFLib.PDFDocument.load(bytes);
                pages = pdf.getPageCount();
                if (!pages || pages > 200) throw new Error('Choose a PDF with 1–200 pages.');
            } else if (isJPG) {
                const image = await createImageBitmap(file);
                const pixels = image.width * image.height;
                image.close();
                if (pixels > 40000000) throw new Error('This image is too large. Resize it to under 40 megapixels.');
                pages = 1;
            } else {
                throw new Error('Choose a valid JPG, JPEG, or PDF file.');
            }
            if (attempt !== entry.attempt || generation !== currentGeneration) return;
            // Recheck after async validation, including other files selected in the meantime.
            if (entries.reduce((sum, item) => sum + (item.file?.size || 0), 0) + file.size > maxTotal) throw new Error('The files exceed 100 MB total. Choose smaller files.');
            entry.file = file;
            entry.pages = pages;
            entry.kind = isPDF ? 'pdf' : 'jpg';
            entry.card.classList.add('is-ready');
            entry.remove.hidden = false;
            entry.details.textContent = `${file.name} · ${pages} ${pages === 1 ? 'page' : 'pages'} · ${(file.size / 1024 / 1024).toFixed(1)} MB`;
        } catch (error) {
            if (attempt !== entry.attempt || generation !== currentGeneration) return;
            entry.details.textContent = (error.name === 'EncryptedPDFError' || /encrypted/i.test(error.message)) ? 'Password-protected PDFs are not supported. Choose an unlocked copy.' : (error.message.startsWith('Choose ') || error.message.startsWith('This ') || error.message.startsWith('Please ') || error.message.startsWith('The ') ? error.message : 'This file could not be read. Choose a valid, unlocked PDF or JPG.');
            entry.card.classList.add('has-error');
        } finally {
            if (attempt === entry.attempt && generation === currentGeneration) {
                entry.loading = false;
                update();
            }
        }
    }
    function render() {
        invalidate();
        generation++;
        const length = Number(count.value);
        // Retain files in existing boxes when the number changes.
        entries = entries.slice(0, length);
        while (entries.length < length) entries.push({file: null, pages: 0, attempt: 0});
        slots.replaceChildren();
        entries.forEach((entry, index) => {
            entry.loading = false;
            entry.attempt++;
            const card = document.createElement('div');
            card.className = 'page-slot' + (entry.file ? ' is-ready' : '');
            const label = document.createElement('label');
            label.className = 'page-drop';
            const title = document.createElement('strong');
            title.textContent = `Page ${index + 1}`;
            const prompt = document.createElement('span');
            prompt.textContent = 'Drop JPG or PDF here';
            const browse = document.createElement('span');
            browse.className = 'page-browse';
            browse.textContent = 'or choose a file';
            const input = document.createElement('input');
            input.type = 'file';
            input.accept = '.jpg,.jpeg,.pdf,image/jpeg,application/pdf';
            input.className = 'page-file-input';
            input.setAttribute('aria-label', `Choose JPG or PDF for page ${index + 1}`);
            const details = document.createElement('p');
            details.className = 'page-details';
            details.id = `page-details-${index}`;
            details.setAttribute('aria-live', 'polite');
            details.textContent = entry.file ? `${entry.file.name} · ${entry.pages} ${entry.pages === 1 ? 'page' : 'pages'}` : 'No file selected';
            input.setAttribute('aria-describedby', details.id);
            const remove = document.createElement('button');
            remove.type = 'button';
            remove.className = 'page-remove';
            remove.textContent = 'Remove file';
            remove.setAttribute('aria-label', `Remove file from page ${index + 1}`);
            remove.hidden = !entry.file;
            Object.assign(entry, {card, input, details, remove});
            input.addEventListener('change', () => { card.classList.remove('has-error'); choose(entry, [...input.files]); });
            remove.addEventListener('click', () => {
                entry.attempt++;
                entry.loading = false;
                invalidate();
                clearEntry(entry);
                details.textContent = 'No file selected';
                card.classList.remove('has-error');
                update();
                input.focus();
            });
            card.addEventListener('dragover', event => { event.preventDefault(); if (!busy) card.classList.add('is-dragging'); });
            card.addEventListener('dragleave', event => { if (!card.contains(event.relatedTarget)) card.classList.remove('is-dragging'); });
            card.addEventListener('drop', event => {
                event.preventDefault();
                card.classList.remove('is-dragging', 'has-error');
                choose(entry, [...event.dataTransfer.files]);
            });
            label.append(title, prompt, browse, input);
            card.append(label, details, remove);
            slots.append(card);
        });
        $('upload-step').hidden = !length;
        $('filename-step').hidden = !length;
        update();
    }
    count.addEventListener('change', render);
    filename.addEventListener('input', () => { invalidate(); update(); });
    $('clear-files').addEventListener('click', () => {
        count.value = '';
        filename.value = '';
        render();
        count.focus();
    });
    // Prevent accidental navigation when a file misses a drop box.
    window.addEventListener('dragover', event => { if ([...event.dataTransfer.types].includes('Files')) event.preventDefault(); });
    window.addEventListener('drop', event => { if ([...event.dataTransfer.types].includes('Files')) event.preventDefault(); });

    $('combiner').addEventListener('submit', async event => {
        event.preventDefault();
        if ($('combine').disabled || busy) return;
        invalidate();
        busy = true;
        controls.disabled = true;
        $('combiner').setAttribute('aria-busy', 'true');
        update();
        try {
            const output = await PDFLib.PDFDocument.create();
            for (const [index, entry] of entries.entries()) {
                status.textContent = `Combining file ${index + 1} of ${entries.length}…`;
                await new Promise(resolve => setTimeout(resolve, 0));
                if (entry.kind === 'pdf') {
                    const source = await PDFLib.PDFDocument.load(await entry.file.arrayBuffer());
                    // Flatten form values before copying pages to preserve filled-in content.
                    const form = source.getForm();
                    if (form.getFields().length) form.flatten();
                    const pages = await output.copyPages(source, source.getPageIndices());
                    pages.forEach(page => output.addPage(page));
                } else {
                    // Browser decoding honours camera orientation before fitting the JPG on A4.
                    const bitmap = await createImageBitmap(entry.file);
                    const canvas = document.createElement('canvas');
                    canvas.width = bitmap.width;
                    canvas.height = bitmap.height;
                    canvas.getContext('2d').drawImage(bitmap, 0, 0);
                    bitmap.close();
                    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.95));
                    canvas.width = canvas.height = 0;
                    if (!blob) throw new Error('Image conversion failed.');
                    const image = await output.embedJpg(await blob.arrayBuffer());
                    const size = image.width > image.height ? [841.89, 595.28] : [595.28, 841.89];
                    const page = output.addPage(size);
                    const scale = Math.min(size[0] / image.width, size[1] / image.height);
                    const width = image.width * scale, height = image.height * scale;
                    page.drawImage(image, {x: (size[0] - width) / 2, y: (size[1] - height) / 2, width, height});
                }
            }
            const bytes = await output.save();
            let name = filename.value.trim().replace(/\.pdf$/i, '').replace(/[<>:"/\\|?*\x00-\x1f]/g, '-').replace(/[. ]+$/g, '').trim();
            if (!name) name = 'combined';
            name += '.pdf';
            resultURL = URL.createObjectURL(new Blob([bytes], {type: 'application/pdf'}));
            $('download-pdf').href = resultURL;
            $('download-pdf').download = name;
            $('result-details').textContent = `${name} · ${output.getPageCount()} ${output.getPageCount() === 1 ? 'page' : 'pages'} · ${(bytes.length / 1024 / 1024).toFixed(1)} MB`;
            $('download-result').hidden = false;
            status.textContent = 'Done. Your combined PDF is ready to download.';
            $('download-pdf').focus();
        } catch (error) {
            status.textContent = 'We could not combine these files. Try smaller files or replace any damaged or unsupported PDF. Your originals have not been changed.';
        } finally {
            busy = false;
            controls.disabled = false;
            $('combiner').removeAttribute('aria-busy');
            update();
        }
    });
    if (!window.PDFLib) status.textContent = 'The PDF engine could not load. Refresh the page and try again.';
})();

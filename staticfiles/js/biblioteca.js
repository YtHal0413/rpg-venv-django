// Bloco: pesquisa, filtra e visualiza arquivos da biblioteca.
(() => {
    const root = document.getElementById("painel_visualizador");
    if (!root) return;

    const list = document.getElementById("lista_arquivos");
    const searchInput = document.getElementById("campo_busca");
    const filterSelect = document.getElementById("filtro_arquivo");
    const emptyPanel = document.getElementById("painel_vazio");
    const readerPanel = document.getElementById("painel_leitor");
    const loadingOverlay = document.getElementById("leitor_carregando");
    const title = document.getElementById("leitor_titulo");
    const pdfContainer = document.getElementById("conteiner_paginas");
    const imageContainer = document.getElementById("conteiner_imagem");
    const imagePreview = document.getElementById("imagem_visualizada");
    const errorPanel = document.getElementById("mensagem_leitor");
    const zoomOutButton = document.getElementById("zoom_out");
    const zoomInButton = document.getElementById("zoom_in");
    const zoomLabel = document.getElementById("zoom_valor");
    const uploadInput = document.getElementById("id_arquivo");
    const uploadLabel = document.getElementById("texto_upload");

    const minZoom = 0.6;
    const maxZoom = 2.5;
    const zoomStep = 0.2;
    let activeFilter = "all";
    let activeFileType = null;
    let activeFileUrl = null;
    let activePdf = null;
    let activePdfLoadingTask = null;
    let activePageObserver = null;
    let renderTasks = new Set();
    let renderQueue = [];
    let activeRenderCount = 0;
    let renderGeneration = 0;
    let zoom = 1;
    let basePdfScale = 1;
    let imageFitScale = 1;

    if (window.pdfjsLib) {
        window.pdfjsLib.GlobalWorkerOptions.workerSrc =
        "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.16.105/pdf.worker.min.js";
    }

    function updateZoomControls() {
        const percentage = Math.round(zoom * 100);
        zoomLabel.textContent = `${percentage}%`;
        zoomOutButton.disabled = zoom <= minZoom;
        zoomInButton.disabled = zoom >= maxZoom;
    }

    function cancelPageRendering(destroyPdf = false) {
        renderGeneration += 1;
        renderQueue = [];

        if (activePageObserver) {
            activePageObserver.disconnect();
            activePageObserver = null;
        }

        for (const task of renderTasks) {
            task.cancel();
        }
        renderTasks = new Set();

        if (activePdfLoadingTask) {
            activePdfLoadingTask.destroy().catch(error => {
                if (error.name !== "AbortException") {
                    console.error("Falha ao cancelar o carregamento do PDF.", error);
                }
            });
            activePdfLoadingTask = null;
        }

        if (destroyPdf && activePdf) {
            activePdf.destroy().catch(error => {
                if (error.name !== "AbortException") {
                    console.error("Falha ao liberar o documento PDF.", error);
                }
            });
            activePdf = null;
        }
    }

    function showLoading(show) {
        loadingOverlay.classList.toggle("hidden", !show);
    }

    function showError(message) {
        errorPanel.textContent = message;
        errorPanel.classList.remove("hidden");
    }

    function clearPreview() {
        cancelPageRendering(true);
        activeFileType = null;
        activeFileUrl = null;
        pdfContainer.replaceChildren();
        imagePreview.removeAttribute("src");
        pdfContainer.classList.add("hidden");
        imageContainer.classList.add("hidden");
        errorPanel.classList.add("hidden");
        showLoading(false);
    }

    function applyFileFilter() {
        const query = searchInput.value.trim().toLocaleLowerCase("pt-BR");
        const items = list.querySelectorAll(".item-arquivo");
        let visibleCount = 0;

        for (const item of items) {
            const matchesType = activeFilter === "all" ||
            item.dataset.fileType === activeFilter;
            const matchesQuery = item.dataset.fileName
            .toLocaleLowerCase("pt-BR")
            .includes(query);
            const visible = matchesType && matchesQuery;
            item.classList.toggle("hidden", !visible);
            if (visible) visibleCount += 1;
        }

        const emptyList = document.getElementById("lista_vazia");
        const noResults = document.getElementById("sem_resultados");
        if (noResults) {
            noResults.classList.toggle("hidden", items.length === 0 || visibleCount > 0);
        }
        if (emptyList) {
            emptyList.classList.toggle(
            "hidden",
            items.length > 0 || (activeFilter === "all" && query === "")
            );
        }
    }

    function shortenUploadName(filename) {
        const characters = Array.from(filename);
        return characters.length > 17
        ? `${characters.slice(0, 17).join("")}...`
        : filename;
    }

    function setActiveItem(selectedButton) {
        for (const button of list.querySelectorAll(".arquivo-selecao")) {
            const selected = button === selectedButton;
            button.closest(".item-arquivo").classList.toggle(
            "arquivo-selecionado",
            selected
            );
            button.setAttribute("aria-current", selected ? "true" : "false");
        }
    }

    function queuePage(pageNumber, pageElement, generation) {
        if (pageElement.dataset.rendered === "true" ||
        pageElement.dataset.queued === "true") {
            return;
        }

        pageElement.dataset.queued = "true";
        renderQueue.push({ pageNumber, pageElement, generation });
        processRenderQueue();
    }

    async function processRenderQueue() {
        if (!activePdf || activeRenderCount >= 2 || renderQueue.length === 0) {
            return;
        }

        const job = renderQueue.shift();
        if (!job || job.generation !== renderGeneration) {
            processRenderQueue();
            return;
        }

        activeRenderCount += 1;
        try {
            const page = await activePdf.getPage(job.pageNumber);
            if (job.generation !== renderGeneration) return;

            const viewport = page.getViewport({ scale: basePdfScale * zoom });
            const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
            const canvas = document.createElement("canvas");
            canvas.className = "pdf-page-canvas";
            canvas.width = Math.ceil(viewport.width * pixelRatio);
            canvas.height = Math.ceil(viewport.height * pixelRatio);
            canvas.style.width = `${viewport.width}px`;
            canvas.style.height = `${viewport.height}px`;
            job.pageElement.replaceChildren(canvas);
            job.pageElement.style.width = `${viewport.width}px`;
            job.pageElement.style.height = `${viewport.height}px`;

            const context = canvas.getContext("2d", { alpha: false });
            if (!context) {
                throw new Error("Não foi possível inicializar o canvas.");
            }
            const renderParameters = {
                canvasContext: context,
                viewport,
            };
            if (pixelRatio !== 1) {
                renderParameters.transform = [
                pixelRatio,
                0,
                0,
                pixelRatio,
                0,
                0,
                ];
            }
            const task = page.render(renderParameters);
            renderTasks.add(task);
            await task.promise;
            renderTasks.delete(task);

            if (job.generation === renderGeneration) {
                job.pageElement.dataset.rendered = "true";
            }
        } catch (error) {
            if (error.name !== "RenderingCancelledException" &&
            job.generation === renderGeneration) {
                showError("Não foi possível renderizar uma página deste PDF.");
                console.error("Falha ao renderizar página do PDF.", error);
            }
        } finally {
            activeRenderCount -= 1;
            processRenderQueue();
        }
    }

    async function renderPdfPages(pdf, generation) {
        const firstPage = await pdf.getPage(1);
        if (generation !== renderGeneration) return;

        pdfContainer.classList.remove("hidden");
        imageContainer.classList.add("hidden");
        const unscaledViewport = firstPage.getViewport({ scale: 1 });
        const availableWidth = Math.max(pdfContainer.clientWidth - 40, 240);
        basePdfScale = Math.min(1.25, availableWidth / unscaledViewport.width);
        pdfContainer.replaceChildren();

        const firstViewport = firstPage.getViewport({ scale: basePdfScale * zoom });
        const fragment = document.createDocumentFragment();
        for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
            const wrapper = document.createElement("section");
            wrapper.className = "pdf-page-shell";
            wrapper.dataset.pageNumber = String(pageNumber);

            const pageSurface = document.createElement("div");
            pageSurface.className = "pdf-page-surface";
            pageSurface.style.width = `${firstViewport.width}px`;
            pageSurface.style.height = `${firstViewport.height}px`;
            pageSurface.dataset.queued = "false";

            const pageLabel = document.createElement("p");
            pageLabel.className = "text-[9px] font-mono font-bold ui-text-muted uppercase tracking-widest";
            pageLabel.textContent = `Pág. ${pageNumber} / ${pdf.numPages}`;

            wrapper.append(pageSurface, pageLabel);
            fragment.appendChild(wrapper);
        }
        pdfContainer.appendChild(fragment);

        activePageObserver = new IntersectionObserver(
        entries => {
            for (const entry of entries) {
                if (!entry.isIntersecting) continue;
                const pageElement = entry.target.querySelector(".pdf-page-surface");
                if (!pageElement) continue;
                const pageNumber = Number(entry.target.dataset.pageNumber);
                queuePage(pageNumber, pageElement, generation);
            }
        },
        {
            root: pdfContainer,
            rootMargin: "600px 0px",
            threshold: 0.01,
        }
        );

        for (const pageElement of pdfContainer.querySelectorAll(".pdf-page-shell")) {
            activePageObserver.observe(pageElement);
        }
    }

    async function openPdf(url, generation) {
        if (!window.pdfjsLib) {
            throw new Error("O visualizador de PDF não está disponível.");
        }

        const loadingTask = window.pdfjsLib.getDocument({
            url,
            isEvalSupported: false,
            enableXfa: false,
            disableStream: true,
            disableAutoFetch: true,
        });
        activePdfLoadingTask = loadingTask;
        const pdf = await loadingTask.promise;
        if (generation !== renderGeneration) {
            await pdf.destroy();
            return;
        }

        activePdfLoadingTask = null;
        activePdf = pdf;
        await renderPdfPages(pdf, generation);
    }

    function openImage(url, generation) {
        pdfContainer.classList.add("hidden");
        imageContainer.classList.remove("hidden");
        imagePreview.onload = () => {
            if (generation !== renderGeneration) return;
            const availableWidth = Math.max(imageContainer.clientWidth - 40, 240);
            const availableHeight = Math.max(imageContainer.clientHeight - 40, 240);
            imageFitScale = Math.min(
            1,
            availableWidth / imagePreview.naturalWidth,
            availableHeight / imagePreview.naturalHeight
            );
            applyImageZoom();
            showLoading(false);
        };
        imagePreview.onerror = () => {
            if (generation !== renderGeneration) return;
            showLoading(false);
            showError("Não foi possível exibir esta imagem.");
        };
        imagePreview.src = url;
    }

    function applyImageZoom() {
        imagePreview.style.width = `${imagePreview.naturalWidth * imageFitScale * zoom}px`;
        imagePreview.style.height = `${imagePreview.naturalHeight * imageFitScale * zoom}px`;
    }

    async function selectFile(button) {
        clearPreview();
        const generation = renderGeneration;
        activeFileType = button.dataset.fileType;
        activeFileUrl = button.dataset.previewUrl;
        zoom = 1;
        updateZoomControls();
        setActiveItem(button);
        title.textContent = button.dataset.fileName;
        emptyPanel.classList.add("hidden");
        readerPanel.classList.remove("hidden");
        showLoading(true);

        try {
            if (activeFileType === "documento") {
                await openPdf(activeFileUrl, generation);
                if (generation === renderGeneration) showLoading(false);
            } else {
                openImage(activeFileUrl, generation);
            }
        } catch (error) {
            if (generation !== renderGeneration) return;
            showLoading(false);
            showError("Não foi possível abrir o arquivo. Verifique se ele está íntegro.");
            console.error("Falha ao abrir arquivo da biblioteca.", error);
        }
    }

    function updateZoom(delta) {
        const nextZoom = Math.min(maxZoom, Math.max(minZoom, zoom + delta));
        if (nextZoom === zoom) return;
        zoom = Math.round(nextZoom * 10) / 10;
        updateZoomControls();

        if (activeFileType === "handout" && imagePreview.complete) {
            applyImageZoom();
        } else if (activeFileType === "documento" && activePdf) {
            const previousScrollTop = pdfContainer.scrollTop;
            cancelPageRendering();
            const generation = renderGeneration;
            showLoading(true);
            renderPdfPages(activePdf, generation)
            .then(() => {
                if (generation !== renderGeneration) return;
                pdfContainer.scrollTop = previousScrollTop;
                showLoading(false);
            })
            .catch(error => {
                if (generation !== renderGeneration) return;
                showLoading(false);
                showError("Não foi possível aplicar o zoom ao PDF.");
                console.error("Falha ao atualizar zoom do PDF.", error);
            });
        }
    }

    searchInput.addEventListener("input", applyFileFilter);
    filterSelect.addEventListener("change", () => {
        activeFilter = filterSelect.value;
        applyFileFilter();
    });

    list.addEventListener("click", event => {
        const button = event.target.closest(".arquivo-selecao");
        if (button) selectFile(button);
    });

    zoomOutButton.addEventListener("click", () => updateZoom(-zoomStep));
    zoomInButton.addEventListener("click", () => updateZoom(zoomStep));
    if (uploadInput) {
        uploadInput.addEventListener("change", () => {
            const filename = uploadInput.files.length
            ? uploadInput.files[0].name
            : "";
            uploadLabel.textContent = filename
            ? shortenUploadName(filename)
            : "Fazer upload de arquivo";
            uploadLabel.title = filename;
        });
    }

    updateZoomControls();
    applyFileFilter();
})();

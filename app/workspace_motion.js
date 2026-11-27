(() => {
    const PAGE_SELECTOR = '[class*="st-key-workspace_page_"]';
    const MAX_SECTIONS = 6;

    function pageIndex(page) {
        const key = [...page.classList].find(name => name.startsWith("st-key-workspace_page_"));
        return Number(key.slice("st-key-workspace_page_".length));
    }

    function visibleSections(page) {
        const viewport = page.closest('[data-testid="stMain"]')?.getBoundingClientRect();
        const top = Math.max(0, viewport?.top ?? 0);
        const bottom = Math.min(window.innerHeight, viewport?.bottom ?? window.innerHeight);
        // Streamlit fragments group their output in an extra vertical block.
        const first = page.firstElementChild;
        const nested = first?.matches('[data-testid="stLayoutWrapper"]') ? first.firstElementChild : first;
        const group = page.childElementCount === 1 && nested?.matches('[data-testid="stVerticalBlock"]')
            ? nested : page;
        const sections = [];
        for (const element of group.children) {
            const bounds = element.getBoundingClientRect();
            if (bounds.width && bounds.height && bounds.bottom > top && bounds.top < bottom) {
                sections.push({element, bounds});
                if (sections.length === MAX_SECTIONS) break;
            }
        }
        return sections;
    }

    function copySection(element) {
        const copy = element.cloneNode(true);
        copy.querySelectorAll("iframe, object, embed, script, audio, video").forEach(node => node.remove());
        copy.removeAttribute("id");
        for (const node of copy.querySelectorAll("[id]")) {
            if (node instanceof HTMLElement) node.removeAttribute("id");
        }
        copy.querySelectorAll("input[name]").forEach(node => node.removeAttribute("name"));

        // Copies keep a canvas's layout but lose its pixels, including dataframe cells.
        const canvases = element.querySelectorAll("canvas");
        copy.querySelectorAll("canvas").forEach((canvas, index) => {
            const original = canvases[index];
            if (original?.width && original.height) {
                canvas.getContext("2d")?.drawImage(original, 0, 0);
            }
        });
        return copy;
    }

    function mountWorkspaceMotion(script) {
        const stage = script?.closest(".st-key-workspace_stage");
        const app = stage?.closest(".stApp");
        if (!app || !Element.prototype.animate || !window.ResizeObserver ||
            stage.hasAttribute("data-workspace-controller")) return;
        stage.setAttribute("data-workspace-controller", "");

        const motion = window.matchMedia("(prefers-reduced-motion: no-preference)");
        const listeners = new AbortController();
        const animations = new Set();
        let previous;
        let arrival;
        let departure;
        let frame = 0;

        function cancelMotion() {
            animations.forEach(animation => animation.cancel());
            animations.clear();
            departure?.remove();
            departure = undefined;
            arrival = undefined;
            stage.removeAttribute("data-workspace-arriving");
        }

        function play(element, keyframes, options) {
            const animation = element.animate(keyframes, options);
            animations.add(animation);
            animation.finished.catch(() => {}).finally(() => {
                animations.delete(animation);
                if (!animations.size) stage.removeAttribute("data-workspace-arriving");
                schedule();
            });
            return animation.finished;
        }

        function slideOut(sections, distance) {
            if (!sections.length) return;
            const layer = document.createElement("div");
            layer.className = "workspace-departure";
            layer.ariaHidden = "true";
            layer.inert = true;
            for (const {element, bounds} of sections) {
                const frame = document.createElement("div");
                Object.assign(frame.style, {
                    left: `${bounds.left}px`, top: `${bounds.top}px`, width: `${bounds.width}px`,
                });
                frame.append(copySection(element));
                layer.append(frame);
            }
            app.append(layer);
            departure = layer;
            const exits = [...layer.children].map((section, index) => play(section, [
                {opacity: 1, transform: "translateX(0)"},
                {offset: .58, opacity: .15, transform: `translateX(${-distance * .75}px)`},
                {opacity: 0, transform: `translateX(${-distance}px)`},
            ], {duration: 245, delay: Math.min(index * 14, 56), easing: "ease-out", fill: "both"}));
            Promise.allSettled(exits).then(() => {
                layer.remove();
                if (departure === layer) departure = undefined;
            });
        }

        function syncPage() {
            if (!motion.matches) return;
            const page = stage.querySelector(PAGE_SELECTOR);
            if (!page) return;
            const index = pageIndex(page);
            if (previous && index !== previous.index) {
                cancelMotion();
                const distance = Math.sign(index - previous.index) * Math.min(80, stage.clientWidth * .075);
                slideOut(previous.sections, distance);
                arrival = {distance, slots: new Set(), until: undefined};
            }

            const sections = visibleSections(page);
            const ready = arrival && sections.filter(({element}) => !element.matches('[data-stale="true"]'));
            if (ready?.length) {
                arrival.until ??= performance.now() + 180;
                if (performance.now() <= arrival.until) {
                    for (const [slot, {element}] of ready.entries()) {
                        if (arrival.slots.has(slot)) continue;
                        arrival.slots.add(slot);
                        stage.setAttribute("data-workspace-arriving", "");
                        play(element, [
                            {opacity: .15, transform: `translateX(${arrival.distance}px)`},
                            {opacity: 1, transform: "translateX(0)"},
                        ], {
                            duration: 330, delay: 35 + Math.min(slot * 20, 85),
                            easing: "ease-out", fill: "backwards",
                        });
                    }
                } else {
                    arrival = undefined;
                }
            }
            previous = {index, sections};
        }

        function schedule() {
            if (!frame && !listeners.signal.aborted) {
                frame = requestAnimationFrame(() => {
                    frame = 0;
                    syncPage();
                });
            }
        }

        function setMotionPreference() {
            stage.toggleAttribute("data-workspace-motion", motion.matches);
            cancelMotion();
            previous = undefined;
            schedule();
        }

        const observer = new MutationObserver(mutations => {
            if (!stage.isConnected) {
                disconnect();
            } else if (mutations.some(mutation => stage.contains(mutation.target))) {
                schedule();
            }
        });
        observer.observe(app, {
            childList: true, subtree: true, attributes: true, attributeFilter: ["data-stale"],
        });
        const resize = new ResizeObserver(schedule);
        resize.observe(stage);
        app.addEventListener("scroll", schedule, {capture: true, passive: true, signal: listeners.signal});
        window.addEventListener("resize", schedule, {passive: true, signal: listeners.signal});
        motion.addEventListener("change", setMotionPreference, {signal: listeners.signal});
        setMotionPreference();

        function disconnect() {
            observer.disconnect();
            resize.disconnect();
            listeners.abort();
            cancelAnimationFrame(frame);
            cancelMotion();
            stage.removeAttribute("data-workspace-motion");
            stage.removeAttribute("data-workspace-controller");
        }
    }

    mountWorkspaceMotion(document.currentScript);
})();

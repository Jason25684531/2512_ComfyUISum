(function (root) {
    "use strict";

    function clamp(value, minimum, maximum) {
        return Math.min(maximum, Math.max(minimum, value));
    }

    function promptFor(horizontalAngle, verticalAngle, zoom) {
        const horizontal = ((Number(horizontalAngle) % 360) + 360) % 360;
        const vertical = Number(verticalAngle);
        const distance = Number(zoom);
        const directions = [
            "front view", "front-right quarter view", "right side view", "back-right quarter view",
            "back view", "back-left quarter view", "left side view", "front-left quarter view"
        ];
        const horizontalDirection = directions[Math.floor(((horizontal + 22.5) % 360) / 45)];
        const verticalDirection = vertical < -15 ? "low-angle shot"
            : vertical < 15 ? "eye-level shot"
                : vertical < 45 ? "elevated shot" : "high-angle shot";
        const distanceDirection = distance < 2 ? "wide shot" : distance < 6 ? "medium shot" : "close-up";
        return `<sks> ${horizontalDirection} ${verticalDirection} ${distanceDirection}`;
    }

    class MultiangleCameraControl {
        constructor(mount) {
            this.values = { horizontal_angle: 0, vertical_angle: 45, zoom: 5 };
            this.mount = mount;
            this._build();
            this.setValues(this.values);
        }

        _build() {
            this.mount.replaceChildren();
            const panel = document.createElement("div");
            panel.className = "grid grid-cols-1 md:grid-cols-[1fr_auto] gap-3 rounded-xl border border-violet-500/30 bg-black/20 p-3";
            this.pad = document.createElement("div");
            this.pad.className = "min-h-24 rounded-lg border border-dashed border-violet-400/50 flex items-center justify-center text-xs text-violet-200 select-none touch-none cursor-grab";
            this.pad.textContent = "拖曳：水平角度／垂直角度；滾輪：縮放";
            panel.appendChild(this.pad);

            const controls = document.createElement("div");
            controls.className = "grid grid-cols-3 gap-2";
            this.inputs = {};
            this.sliders = {};
            [["horizontal_angle", "水平", 0, 360, 1], ["vertical_angle", "垂直", -30, 60, 1], ["zoom", "Zoom", 0, 10, 0.1]].forEach(([name, label, minimum, maximum, step]) => {
                const wrapper = document.createElement("label");
                wrapper.className = "flex flex-col gap-1 text-xs text-gray-300";
                wrapper.textContent = label;
                const input = document.createElement("input");
                input.type = "number";
                input.min = String(minimum);
                input.max = String(maximum);
                input.step = String(step);
                input.className = "w-20 bg-black/30 border border-white/10 rounded px-2 py-1 text-white";
                input.addEventListener("input", () => this._readInput(name));
                wrapper.appendChild(input);
                const slider = document.createElement("input");
                slider.type = "range";
                slider.min = String(minimum);
                slider.max = String(maximum);
                slider.step = String(step);
                slider.className = "w-full accent-violet-500";
                slider.addEventListener("input", () => this.setValues({ [name]: Number(slider.value) }));
                wrapper.appendChild(slider);
                controls.appendChild(wrapper);
                this.inputs[name] = input;
                this.sliders[name] = slider;
            });
            panel.appendChild(controls);

            this.preview = document.createElement("p");
            this.preview.className = "col-span-full text-xs text-violet-200 break-all";
            this.error = document.createElement("p");
            this.error.className = "col-span-full text-xs text-red-300";
            panel.append(this.preview, this.error);
            this.mount.appendChild(panel);

            this.pad.addEventListener("pointerdown", (event) => {
                this.drag = { x: event.clientX, y: event.clientY };
                this.pad.setPointerCapture(event.pointerId);
                this.pad.classList.replace("cursor-grab", "cursor-grabbing");
            });
            this.pad.addEventListener("pointermove", (event) => {
                if (!this.drag) return;
                this.setValues({ horizontal_angle: this.values.horizontal_angle + event.clientX - this.drag.x, vertical_angle: this.values.vertical_angle - (event.clientY - this.drag.y) });
                this.drag = { x: event.clientX, y: event.clientY };
            });
            this.pad.addEventListener("pointerup", (event) => this._endDrag(event));
            this.pad.addEventListener("pointercancel", (event) => this._endDrag(event));
            this.pad.addEventListener("wheel", (event) => {
                event.preventDefault();
                this.setValues({ zoom: this.values.zoom + (event.deltaY > 0 ? -0.1 : 0.1) });
            }, { passive: false });
        }

        _endDrag(event) {
            this.drag = null;
            if (this.pad.hasPointerCapture(event.pointerId)) this.pad.releasePointerCapture(event.pointerId);
            this.pad.classList.replace("cursor-grabbing", "cursor-grab");
        }

        _readInput(name) {
            const value = Number(this.inputs[name].value);
            if (!Number.isFinite(value)) {
                this.error.textContent = "請輸入有效數字。";
                return;
            }
            this.error.textContent = "";
            this.setValues({ [name]: value });
        }

        setValues(next) {
            const horizontal = Number(next.horizontal_angle ?? this.values.horizontal_angle);
            const vertical = Number(next.vertical_angle ?? this.values.vertical_angle);
            const zoom = Number(next.zoom ?? this.values.zoom);
            this.values = {
                horizontal_angle: ((Math.round(horizontal) % 360) + 360) % 360,
                vertical_angle: Math.round(clamp(vertical, -30, 60)),
                zoom: Number(clamp(zoom, 0, 10).toFixed(1))
            };
            Object.entries(this.values).forEach(([name, value]) => {
                this.inputs[name].value = String(value);
                this.sliders[name].value = String(value);
            });
            this.preview.textContent = promptFor(this.values.horizontal_angle, this.values.vertical_angle, this.values.zoom);
        }

        getValues() { return { ...this.values }; }
        static selfCheck() {
            if (promptFor(0, 45, 5) !== "<sks> front view high-angle shot medium shot") throw new Error("multi-angle prompt regression");
            if (!promptFor(22.5, 0, 5).includes("front-right quarter view")) throw new Error("horizontal boundary regression");
            if (!promptFor(0, -15, 5).includes("eye-level shot")) throw new Error("vertical boundary regression");
            if (!promptFor(0, 0, 6).includes("close-up")) throw new Error("zoom boundary regression");
        }
    }

    MultiangleCameraControl.selfCheck();
    root.MultiangleCameraControl = MultiangleCameraControl;
    if (typeof module !== "undefined" && module.exports) module.exports = { promptFor, MultiangleCameraControl };
}(typeof window !== "undefined" ? window : globalThis));

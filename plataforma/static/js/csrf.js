(function () {
    const fetchOriginal = window.fetch.bind(window);
    window.fetch = function (resource, options) {
        const requestOptions = options || {};
        const method = (requestOptions.method || "GET").toUpperCase();
        const url = new URL(typeof resource === "string" ? resource : resource.url, window.location.href);

        if (url.origin === window.location.origin && !["GET", "HEAD", "OPTIONS", "TRACE"].includes(method)) {
            const cookie = document.cookie.split("; ").find((item) => item.startsWith("csrftoken="));
            const token = cookie ? decodeURIComponent(cookie.split("=").slice(1).join("=")) : "";
            const headers = new Headers(requestOptions.headers || {});
            if (token) headers.set("X-CSRFToken", token);
            return fetchOriginal(resource, { ...requestOptions, headers });
        }

        return fetchOriginal(resource, requestOptions);
    };
})();

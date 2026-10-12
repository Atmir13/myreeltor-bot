"use strict";

const FAVORITES_KEY = "myreeltor_favorites";

function getFavorites() {
    try {
        const value = JSON.parse(localStorage.getItem(FAVORITES_KEY) || "[]");
        return Array.isArray(value) ? value.map(Number) : [];
    } catch (error) {
        console.warn("Не удалось прочитать избранное", error);
        return [];
    }
}

function setFavorites(ids) {
    localStorage.setItem(FAVORITES_KEY, JSON.stringify([...new Set(ids)]));
}

function updateFavoriteButton(button, isFavorite) {
    button.textContent = isFavorite ? "★ Сохранено" : "☆ Сохранить";
    button.classList.toggle("is-favorite", isFavorite);
    button.setAttribute("aria-pressed", String(isFavorite));
}

document.addEventListener("DOMContentLoaded", () => {
    const favorites = getFavorites();
    document.querySelectorAll("[data-property-id]").forEach((button) => {
        const id = Number(button.dataset.propertyId);
        updateFavoriteButton(button, favorites.includes(id));
        button.addEventListener("click", () => {
            const current = getFavorites();
            const index = current.indexOf(id);
            if (index >= 0) current.splice(index, 1);
            else current.push(id);
            setFavorites(current);
            updateFavoriteButton(button, current.includes(id));
        });
    });

    const catalog = document.querySelector("#favorites-catalog");
    if (catalog) {
        const query = getFavorites().join(",");
        if (query) window.location.replace(`/favorites?ids=${encodeURIComponent(query)}`);
    }
});

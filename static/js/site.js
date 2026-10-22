document.getElementById("year").textContent = new Date().getFullYear();

function currentTheme() { return document.documentElement.getAttribute("data-theme"); }
function paintThemeButton() {
  document.getElementById("themeToggle").textContent = currentTheme() === "dark" ? "LIGHT" : "DARK";
}
paintThemeButton();
document.getElementById("themeToggle").addEventListener("click", function () {
  var next = currentTheme() === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("theme", next);
  paintThemeButton();
});

var overlay = document.getElementById("navOverlay");
document.getElementById("menuToggle").addEventListener("click", function () { overlay.classList.add("open"); });
document.getElementById("menuClose").addEventListener("click", function () { overlay.classList.remove("open"); });
overlay.querySelectorAll("a").forEach(function (link) {
  link.addEventListener("click", function () { overlay.classList.remove("open"); });
});

var lightbox = document.getElementById("lightbox");
var lightboxImg = document.getElementById("lightboxImg");
var lightboxThumbs = document.getElementById("lightboxThumbs");
var lightboxBase = "";
var lightboxImages = [];
var lightboxIndex = 0;
var lightboxTitle = "";

function showImage(index) {
  lightboxIndex = (index + lightboxImages.length) % lightboxImages.length;
  lightboxImg.src = lightboxBase + lightboxImages[lightboxIndex];
  lightboxImg.alt = lightboxTitle + " - photo " + (lightboxIndex + 1);
  lightboxThumbs.querySelectorAll("img").forEach(function (t, i) {
    t.classList.toggle("active", i === lightboxIndex);
  });
  var active = lightboxThumbs.children[lightboxIndex];
  if (active) active.scrollIntoView({ block: "nearest", inline: "nearest" });
}

// item: {prefix: "rolls/<slug>" | "albums/<slug>", images, title, label, note, album}
function openLightbox(item, start) {
  lightboxBase = CDN + "/" + item.prefix + "/";
  lightboxImages = item.images;
  lightboxTitle = item.title;
  document.getElementById("lightboxId").textContent = item.label;
  document.getElementById("lightboxTitle").textContent = item.title;
  var noteEl = document.getElementById("lightboxNote");
  noteEl.textContent = item.note || "";
  noteEl.style.display = item.note ? "" : "none";
  var albumEl = document.getElementById("lightboxAlbum");
  albumEl.href = item.album || "#";
  albumEl.style.display = item.album ? "" : "none";
  lightboxThumbs.innerHTML = "";
  item.images.forEach(function (image, index) {
    var thumb = document.createElement("img");
    thumb.src = lightboxBase + "thumb/" + image;
    thumb.alt = item.title + " - thumbnail " + (index + 1);
    thumb.loading = "lazy";
    thumb.addEventListener("click", function () { showImage(index); });
    lightboxThumbs.appendChild(thumb);
  });
  lightbox.classList.add("open");
  showImage(start || 0);
}

function openRoll(p) {
  openLightbox({
    prefix: "rolls/" + p.slug, images: p.images, title: p.title, label: "ROLL · " + p.date,
    note: p.showcase, album: p.album ? "/albums/" + p.album + "/" : "",
  });
}

function closeLightbox() { lightbox.classList.remove("open"); }

document.getElementById("lightboxClose").addEventListener("click", closeLightbox);
document.addEventListener("keydown", function (e) {
  if (!lightbox.classList.contains("open")) return;
  if (e.key === "Escape") closeLightbox();
  if (e.key === "ArrowRight") showImage(lightboxIndex + 1);
  if (e.key === "ArrowLeft") showImage(lightboxIndex - 1);
});

/* cmpload (pages/insights.py): a compare box names its lazy chunk (data-cmp-src); load it only where one is,
   so film pages without a box (archived films) and every other page never fetch it. */
feature(function () {
  var box = q("[data-cmp-src]"), src = box && box.getAttribute("data-cmp-src");
  if (!src) return;
  var s = document.createElement("script"); s.src = src; s.async = true; document.head.appendChild(s);
});

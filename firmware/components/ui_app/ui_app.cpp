// Two-column dashboard: header (time | indoor | Shenzhen weather),
// left CLAUDE (5h/7d bars + today/month/total), right DEEPSEEK (balance).
// Built once in ui_app_init(); update functions only set text/values so the
// reflective panel only redraws on the 60s poll. See docs/mockup.png.

#include "ui_app.h"
#include "icons.h"
#include "lvgl.h"
#include <stdio.h>
#include <string.h>

#define INK   lv_color_black()
#define WHITE lv_color_white()
#define GRAY  lv_color_hex(0x707070)

// dynamic widgets
static lv_obj_t *lbl_time, *lbl_indoor, *img_wx, *lbl_wx_temp, *lbl_wx_city;
static lv_obj_t *bar_5h, *bar_7d, *lbl_5h_pct, *lbl_7d_pct, *lbl_reset;
static lv_obj_t *lbl_c_today, *lbl_c_month, *lbl_c_total;
static lv_obj_t *lbl_ds_bal, *lbl_ds_granted, *lbl_ds_topped, *lbl_ds_today;
static bool have_data;

static void fmt_tok(char *o, size_t n, int64_t t)
{
    if      (t >= 1000000000LL) snprintf(o, n, "%.1fB", t / 1e9);
    else if (t >= 10000000LL)   snprintf(o, n, "%.0fM", t / 1e6);
    else if (t >= 1000000LL)    snprintf(o, n, "%.1fM", t / 1e6);
    else if (t >= 1000LL)       snprintf(o, n, "%.0fk", t / 1e3);
    else                        snprintf(o, n, "%lld", (long long) t);
}
static void fmt_cost(char *o, size_t n, double c)
{
    if      (c < 100)   snprintf(o, n, "$%.2f", c);
    else if (c < 10000) snprintf(o, n, "$%.0f", c);
    else                snprintf(o, n, "$%.1fk", c / 1000.0);
}

static lv_obj_t *mklabel(lv_obj_t *p, int x, int y, const lv_font_t *f, lv_color_t col, const char *t)
{
    lv_obj_t *l = lv_label_create(p);
    lv_obj_set_style_text_font(l, f, 0);
    lv_obj_set_style_text_color(l, col, 0);
    lv_obj_set_pos(l, x, y);
    lv_label_set_text(l, t);
    return l;
}
static void mkdiv(lv_obj_t *p, int x, int y, int w, int h)
{
    lv_obj_t *d = lv_obj_create(p);
    lv_obj_remove_style_all(d);
    lv_obj_set_pos(d, x, y);
    lv_obj_set_size(d, w, h);
    lv_obj_set_style_bg_color(d, lv_color_hex(0xCCCCCC), 0);
    lv_obj_set_style_bg_opa(d, LV_OPA_COVER, 0);
}
static lv_obj_t *mkbar(lv_obj_t *p, int x, int y, int w)
{
    lv_obj_t *b = lv_bar_create(p);
    lv_obj_set_pos(b, x, y);
    lv_obj_set_size(b, w, 12);
    lv_bar_set_range(b, 0, 100);
    lv_obj_set_style_radius(b, 6, 0);
    lv_obj_set_style_bg_color(b, lv_color_hex(0xD0D0D0), LV_PART_MAIN);
    lv_obj_set_style_border_color(b, GRAY, LV_PART_MAIN);
    lv_obj_set_style_border_width(b, 1, LV_PART_MAIN);
    lv_obj_set_style_radius(b, 6, LV_PART_INDICATOR);
    lv_obj_set_style_bg_color(b, INK, LV_PART_INDICATOR);
    lv_bar_set_value(b, 0, LV_ANIM_OFF);
    return b;
}
static lv_obj_t *mkicon(lv_obj_t *p, int x, int y, const lv_image_dsc_t *src)
{
    lv_obj_t *im = lv_image_create(p);
    lv_image_set_src(im, src);
    lv_obj_set_pos(im, x, y);
    lv_obj_set_style_image_recolor(im, INK, 0);
    lv_obj_set_style_image_recolor_opa(im, LV_OPA_COVER, 0);
    return im;
}

void ui_app_init(void)
{
    lv_obj_t *s = lv_screen_active();
    lv_obj_set_style_bg_color(s, WHITE, 0);
    lv_obj_set_style_bg_opa(s, LV_OPA_COVER, 0);

    // ---- header ----
    lbl_time   = mklabel(s, 10, 4, &lv_font_montserrat_28, INK, "--:--");
    lbl_indoor = mklabel(s, 12, 44, &lv_font_montserrat_14, GRAY, "IN --.-\xC2\xB0""C  --%");
    img_wx     = mkicon(s, 250, 8, &icon_wx_cloud);
    lbl_wx_temp = mklabel(s, 286, 12, &lv_font_montserrat_20, INK, "--\xC2\xB0""C");
    lbl_wx_city = mklabel(s, 230, 44, &lv_font_montserrat_14, GRAY, "SHENZHEN");
    mkdiv(s, 10, 64, 380, 2);

    // ---- vertical split ----
    mkdiv(s, 200, 74, 1, 210);

    // ---- left: CLAUDE ----
    mkicon(s, 12, 78, &icon_claudecode);
    mklabel(s, 40, 76, &lv_font_montserrat_16, INK, "CLAUDE");
    mklabel(s, 12, 102, &lv_font_montserrat_14, GRAY, "5h");
    bar_5h = mkbar(s, 40, 103, 96);
    lbl_5h_pct = mklabel(s, 146, 100, &lv_font_montserrat_14, INK, "--%");
    mklabel(s, 12, 124, &lv_font_montserrat_14, GRAY, "7d");
    bar_7d = mkbar(s, 40, 125, 96);
    lbl_7d_pct = mklabel(s, 146, 122, &lv_font_montserrat_14, INK, "--%");
    lbl_reset  = mklabel(s, 12, 146, &lv_font_montserrat_14, GRAY, "reset --");
    mkdiv(s, 12, 168, 178, 1);
    lbl_c_today = mklabel(s, 12, 176, &lv_font_montserrat_14, INK, "today");
    lbl_c_month = mklabel(s, 12, 200, &lv_font_montserrat_14, INK, "month");
    lbl_c_total = mklabel(s, 12, 224, &lv_font_montserrat_14, INK, "total");

    // ---- right: DEEPSEEK ----
    mkicon(s, 212, 78, &icon_deepseek);
    mklabel(s, 240, 76, &lv_font_montserrat_16, INK, "DEEPSEEK");
    mklabel(s, 212, 102, &lv_font_montserrat_14, GRAY, "balance CNY");
    lbl_ds_bal = mklabel(s, 212, 118, &lv_font_montserrat_28, INK, "--");
    mkdiv(s, 212, 168, 178, 1);
    lbl_ds_granted = mklabel(s, 212, 176, &lv_font_montserrat_14, INK, "granted");
    lbl_ds_topped  = mklabel(s, 212, 200, &lv_font_montserrat_14, INK, "topped");
    lbl_ds_today   = mklabel(s, 212, 224, &lv_font_montserrat_14, INK, "today");
    have_data = false;
}

static const lv_image_dsc_t *wx_icon(const char *key)
{
    if (!strcmp(key, "clear"))  return &icon_wx_clear;
    if (!strcmp(key, "partly")) return &icon_wx_partly;
    if (!strcmp(key, "rain"))   return &icon_wx_rain;
    if (!strcmp(key, "snow"))   return &icon_wx_snow;
    if (!strcmp(key, "fog"))    return &icon_wx_fog;
    return &icon_wx_cloud;
}

// right-aligned 2-column row: "label .... value"
static void set_row(lv_obj_t *lbl, const char *name, const char *col1, const char *col2)
{
    char buf[48];
    if (col2) snprintf(buf, sizeof(buf), "%-6s%6s %7s", name, col1, col2);
    else      snprintf(buf, sizeof(buf), "%-8s%9s", name, col1);
    lv_label_set_text(lbl, buf);
}

void ui_app_update(const usage_report_t *r)
{
    if (!r) return;
    have_data = true;
    char tk[16], ct[16];

    // claude bars
    int p5 = r->limits.util_5h_x100, p7 = r->limits.util_7d_x100;
    if (p5 >= 0) { lv_bar_set_value(bar_5h, p5, LV_ANIM_OFF); char b[16]; snprintf(b, 16, "%d%%", p5); lv_label_set_text(lbl_5h_pct, b); }
    if (p7 >= 0) { lv_bar_set_value(bar_7d, p7, LV_ANIM_OFF); char b[16]; snprintf(b, 16, "%d%%", p7); lv_label_set_text(lbl_7d_pct, b); }
    { char b[40]; int m = r->limits.reset_5h_min;
      if (m >= 0) snprintf(b, sizeof(b), "reset in %dh%02dm", m / 60, m % 60);
      else        snprintf(b, sizeof(b), "reset --");
      lv_label_set_text(lbl_reset, b); }

    fmt_tok(tk, sizeof(tk), r->today.tokens_used); fmt_cost(ct, sizeof(ct), r->today.cost_usd);
    set_row(lbl_c_today, "today", tk, ct);
    fmt_tok(tk, sizeof(tk), r->month.tokens_used); fmt_cost(ct, sizeof(ct), r->month.cost_usd);
    set_row(lbl_c_month, "month", tk, ct);
    fmt_tok(tk, sizeof(tk), r->lifetime.tokens_used); fmt_cost(ct, sizeof(ct), r->lifetime.cost_usd);
    set_row(lbl_c_total, "total", tk, ct);

    // deepseek
    if (r->deepseek.valid) {
        char b[24]; snprintf(b, sizeof(b), "%.2f", r->deepseek.balance); lv_label_set_text(lbl_ds_bal, b);
        char g[16]; snprintf(g, sizeof(g), "%.2f", r->deepseek.granted); set_row(lbl_ds_granted, "granted", g, NULL);
        char t[16]; snprintf(t, sizeof(t), "%.2f", r->deepseek.topped);  set_row(lbl_ds_topped, "topped", t, NULL);
        fmt_tok(tk, sizeof(tk), r->deepseek.today_tokens); strncat(tk, " tok", sizeof(tk) - strlen(tk) - 1);
        set_row(lbl_ds_today, "today", tk, NULL);
    }

    // weather (from bridge)
    if (r->weather.valid) {
        lv_image_set_src(img_wx, wx_icon(r->weather.icon));
        char b[16]; snprintf(b, sizeof(b), "%.0f\xC2\xB0""C", r->weather.temp_c);
        lv_label_set_text(lbl_wx_temp, b);
    }
}

void ui_app_set_env(float temp_c, float humidity, bool ok)
{
    char b[32];
    if (ok) snprintf(b, sizeof(b), "IN %.1f\xC2\xB0""C  %.0f%%", temp_c, humidity);
    else    snprintf(b, sizeof(b), "IN --");
    lv_label_set_text(lbl_indoor, b);
}

void ui_app_set_time(const char *hm)
{
    if (lbl_time) lv_label_set_text(lbl_time, hm);
}

void ui_app_mark_stale(void)
{
    if (lbl_time && have_data) {
        // subtle marker; keep last good values
        lv_obj_set_style_text_color(lbl_time, GRAY, 0);
    }
}

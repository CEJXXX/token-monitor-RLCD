// Two-column dashboard: header (time | indoor | Shenzhen weather),
// left CLAUDE (5h/7d bars + today/month/total), right DEEPSEEK (balance).
// Built once in ui_app_init(); update functions only set text/values so the
// reflective panel only redraws on the 60s poll. See docs/mockup.png.
//
// 1-bit panel: everything is pure black (no grayscale). Amounts use a bold
// font (font_amt14); the balance uses a bold ¥-capable font (font_bal28).

#include "ui_app.h"
#include "icons.h"
#include "lvgl.h"
#include <stdio.h>
#include <string.h>

LV_FONT_DECLARE(font_amt14);   // DejaVuSans-Bold 14 (ascii + °)
LV_FONT_DECLARE(font_bal28);   // DejaVuSans-Bold 28 (digits . ¥)

#define INK   lv_color_black()
#define WHITE lv_color_white()

static lv_obj_t *lbl_time, *lbl_indoor, *img_wx, *lbl_wx_temp, *lbl_wx_city;
static lv_obj_t *bar_5h, *bar_7d, *lbl_5h_pct, *lbl_7d_pct, *lbl_reset;
static lv_obj_t *c_tok[3], *c_cost[3];
static lv_obj_t *lbl_ds_bal, *ds_val[3];
static bool have_data;

static void fmt_tok(char *o, size_t n, int64_t t)
{
    if      (t >= 1000000000LL) snprintf(o, n, "%.1fB", t / 1e9);
    else if (t >= 10000000LL)   snprintf(o, n, "%.0fM", t / 1e6);
    else if (t >= 1000000LL)    snprintf(o, n, "%.1fM", t / 1e6);
    else if (t >= 1000LL)       snprintf(o, n, "%.0fk", t / 1e3);
    else                        snprintf(o, n, "%lld", (long long) t);
}
// keep amounts short so they never overflow the column:
//   < $100  -> 2 decimals ($98.42)   $100-999 -> integer ($182)   >= $1000 -> "$X.Xk"
static void fmt_cost(char *o, size_t n, double c)
{
    if      (c < 100)  snprintf(o, n, "$%.2f", c);
    else if (c < 1000) snprintf(o, n, "$%.0f", c);
    else               snprintf(o, n, "$%.1fk", c / 1000.0);
}

static lv_obj_t *mklabel(lv_obj_t *p, int x, int y, const lv_font_t *f, const char *t)
{
    lv_obj_t *l = lv_label_create(p);
    lv_obj_set_style_text_font(l, f, 0);
    lv_obj_set_style_text_color(l, INK, 0);
    lv_obj_set_pos(l, x, y);
    lv_label_set_text(l, t);
    return l;
}
static lv_obj_t *mkalign(lv_obj_t *p, int left_x, int y, int w, lv_text_align_t a,
                         const lv_font_t *f, const char *t)
{
    lv_obj_t *l = lv_label_create(p);
    lv_obj_set_style_text_font(l, f, 0);
    lv_obj_set_style_text_color(l, INK, 0);
    lv_obj_set_width(l, w);
    lv_obj_set_style_text_align(l, a, 0);
    lv_label_set_long_mode(l, LV_LABEL_LONG_CLIP);  // never wrap a fixed column
    lv_obj_set_pos(l, left_x, y);
    lv_label_set_text(l, t);
    return l;
}
static void mkdiv(lv_obj_t *p, int x, int y, int w, int h)
{
    lv_obj_t *d = lv_obj_create(p);
    lv_obj_remove_style_all(d);
    lv_obj_set_pos(d, x, y);
    lv_obj_set_size(d, w, h);
    lv_obj_set_style_bg_color(d, INK, 0);
    lv_obj_set_style_bg_opa(d, LV_OPA_COVER, 0);
}
static lv_obj_t *mkbar(lv_obj_t *p, int x, int y, int w)
{
    lv_obj_t *b = lv_bar_create(p);
    lv_obj_set_pos(b, x, y);
    lv_obj_set_size(b, w, 13);
    lv_bar_set_range(b, 0, 100);
    lv_obj_set_style_radius(b, 6, LV_PART_MAIN);
    lv_obj_set_style_bg_color(b, WHITE, LV_PART_MAIN);
    lv_obj_set_style_bg_opa(b, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_border_color(b, INK, LV_PART_MAIN);
    lv_obj_set_style_border_width(b, 2, LV_PART_MAIN);
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
    lbl_time   = mklabel(s, 10, 4, &lv_font_montserrat_28, "--:--");
    lbl_indoor = mklabel(s, 12, 44, &lv_font_montserrat_14, "IN --.-\xC2\xB0""C  --%RH");
    img_wx     = mkicon(s, 280, 8, &icon_wx_cloud);
    lbl_wx_temp = mkalign(s, 308, 10, 80, LV_TEXT_ALIGN_RIGHT, &lv_font_montserrat_20, "--\xC2\xB0""C");
    lbl_wx_city = mkalign(s, 208, 44, 180, LV_TEXT_ALIGN_RIGHT, &lv_font_montserrat_14, "SHENZHEN");
    mkdiv(s, 10, 66, 380, 2);

    mkdiv(s, 200, 74, 2, 214);   // column split

    // ---- left: CLAUDE ----
    mkicon(s, 10, 72, &icon_claudecode);
    mklabel(s, 50, 76, &lv_font_montserrat_20, "CLAUDE");
    mklabel(s, 12, 112, &lv_font_montserrat_14, "5h");
    bar_5h = mkbar(s, 40, 112, 96);
    lbl_5h_pct = mkalign(s, 140, 110, 52, LV_TEXT_ALIGN_RIGHT, &font_amt14, "--%");
    mklabel(s, 12, 136, &lv_font_montserrat_14, "7d");
    bar_7d = mkbar(s, 40, 136, 96);
    lbl_7d_pct = mkalign(s, 140, 134, 52, LV_TEXT_ALIGN_RIGHT, &font_amt14, "--%");
    lbl_reset  = mklabel(s, 12, 160, &lv_font_montserrat_14, "reset --");
    mkdiv(s, 12, 184, 178, 1);
    const char *crows[3] = {"today", "month", "total"};
    for (int i = 0; i < 3; ++i) {
        int y = 192 + i * 28;
        mklabel(s, 12, y, &lv_font_montserrat_14, crows[i]);
        c_tok[i]  = mkalign(s, 60, y, 64, LV_TEXT_ALIGN_RIGHT, &font_amt14, "-");
        c_cost[i] = mkalign(s, 128, y, 64, LV_TEXT_ALIGN_RIGHT, &font_amt14, "-");
    }

    // ---- right: DEEPSEEK ----
    mkicon(s, 210, 72, &icon_deepseek);
    mklabel(s, 250, 76, &lv_font_montserrat_20, "DEEPSEEK");
    mkalign(s, 212, 104, 176, LV_TEXT_ALIGN_CENTER, &lv_font_montserrat_14, "balance");
    lbl_ds_bal = mkalign(s, 212, 132, 176, LV_TEXT_ALIGN_CENTER, &font_bal28, "\xC2\xA5""0.00");
    mkdiv(s, 212, 184, 178, 1);
    const char *drows[3] = {"granted", "topped", "today"};
    for (int i = 0; i < 3; ++i) {
        int y = 192 + i * 28;
        mklabel(s, 212, y, &lv_font_montserrat_14, drows[i]);
        ds_val[i] = mkalign(s, 268, y, 120, LV_TEXT_ALIGN_RIGHT, &font_amt14, "-");
    }
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

void ui_app_update(const usage_report_t *r)
{
    if (!r) return;
    have_data = true;
    char tk[16], ct[16];

    int p5 = r->limits.util_5h_x100, p7 = r->limits.util_7d_x100;
    if (p5 >= 0) { lv_bar_set_value(bar_5h, p5, LV_ANIM_OFF); char b[16]; snprintf(b, 16, "%d%%", p5); lv_label_set_text(lbl_5h_pct, b); }
    if (p7 >= 0) { lv_bar_set_value(bar_7d, p7, LV_ANIM_OFF); char b[16]; snprintf(b, 16, "%d%%", p7); lv_label_set_text(lbl_7d_pct, b); }
    { char b[40]; int m = r->limits.reset_5h_min;
      if (m >= 0) snprintf(b, sizeof(b), "reset in %dh%02dm", m / 60, m % 60);
      else        snprintf(b, sizeof(b), "reset --");
      lv_label_set_text(lbl_reset, b); }

    const usage_bucket_t *cb[3] = { &r->today, &r->month, &r->lifetime };
    for (int i = 0; i < 3; ++i) {
        fmt_tok(tk, sizeof(tk), cb[i]->tokens_used);  lv_label_set_text(c_tok[i], tk);
        fmt_cost(ct, sizeof(ct), cb[i]->cost_usd);    lv_label_set_text(c_cost[i], ct);
    }

    if (r->deepseek.valid) {
        char b[24];
        snprintf(b, sizeof(b), "\xC2\xA5""%.2f", r->deepseek.balance);  lv_label_set_text(lbl_ds_bal, b);  // ¥
        snprintf(b, sizeof(b), "%.2f", r->deepseek.granted);  lv_label_set_text(ds_val[0], b);
        snprintf(b, sizeof(b), "%.2f", r->deepseek.topped);   lv_label_set_text(ds_val[1], b);
        fmt_tok(tk, sizeof(tk), r->deepseek.today_tokens);
        strncat(tk, " tok", sizeof(tk) - strlen(tk) - 1);     lv_label_set_text(ds_val[2], tk);
    }

    if (r->weather.valid) {
        lv_image_set_src(img_wx, wx_icon(r->weather.icon));
        char b[16]; snprintf(b, sizeof(b), "%.0f\xC2\xB0""C", r->weather.temp_c);
        lv_label_set_text(lbl_wx_temp, b);
        char c[40]; snprintf(c, sizeof(c), "%-8s  %s", r->weather.city, r->weather.condition);
        lv_label_set_text(lbl_wx_city, c);
    }
}

void ui_app_set_env(float temp_c, float humidity, bool ok)
{
    char b[40];
    if (ok) snprintf(b, sizeof(b), "IN %.1f\xC2\xB0""C  %.0f%%RH", temp_c, humidity);
    else    snprintf(b, sizeof(b), "IN --");
    lv_label_set_text(lbl_indoor, b);
}

void ui_app_set_time(const char *hm)
{
    if (lbl_time) lv_label_set_text(lbl_time, hm);
}

void ui_app_mark_stale(void)
{
    // keep last good values; nothing to dim on a 1-bit panel
}

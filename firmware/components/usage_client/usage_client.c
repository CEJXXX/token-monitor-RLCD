#include "usage_client.h"

#include <stdlib.h>
#include <string.h>

#include "cJSON.h"
#include "esp_http_client.h"
#include "esp_log.h"

static const char *TAG = "usage_client";

#define MAX_RESP_BYTES (16 * 1024)

typedef struct {
    char *buf;
    int   len;
    int   cap;
} resp_t;

static esp_err_t http_evt(esp_http_client_event_t *ev)
{
    if (ev->event_id == HTTP_EVENT_ON_DATA && !esp_http_client_is_chunked_response(ev->client)) {
        resp_t *r = (resp_t *) ev->user_data;
        if (r->len + ev->data_len < r->cap) {
            memcpy(r->buf + r->len, ev->data, ev->data_len);
            r->len += ev->data_len;
            r->buf[r->len] = 0;
        }
    }
    return ESP_OK;
}

static int32_t pct_x100(const cJSON *v)
{
    return cJSON_IsNumber(v) ? (int32_t)(v->valuedouble * 10000.0) : -1;
}

static void parse_bucket(const cJSON *o, usage_bucket_t *out)
{
    if (!cJSON_IsObject(o)) {
        out->percent_used_x100 = -1;
        return;
    }
    const cJSON *tok = cJSON_GetObjectItemCaseSensitive(o, "tokens_used");
    const cJSON *cst = cJSON_GetObjectItemCaseSensitive(o, "cost_usd");
    const cJSON *pct = cJSON_GetObjectItemCaseSensitive(o, "percent_used");
    out->tokens_used       = cJSON_IsNumber(tok) ? (int64_t) tok->valuedouble : 0;
    out->cost_usd          = cJSON_IsNumber(cst) ? cst->valuedouble : 0.0;
    out->percent_used_x100 = pct_x100(pct);
}

esp_err_t usage_client_fetch(const char *url, const char *token, usage_report_t *out)
{
    memset(out, 0, sizeof(*out));
    out->active_block.percent_used_x100 = -1;

    char *buf = (char *) malloc(MAX_RESP_BYTES);
    if (!buf) return ESP_ERR_NO_MEM;
    resp_t r = { .buf = buf, .len = 0, .cap = MAX_RESP_BYTES };

    esp_http_client_config_t cfg = {
        .url           = url,
        .event_handler = http_evt,
        .user_data     = &r,
        .timeout_ms    = 30000,   // bridge keeps cache warm, but allow margin for a cold start
    };
    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    if (token && token[0]) {
        esp_http_client_set_header(client, "X-RLCD-Token", token);
    }
    esp_err_t err  = esp_http_client_perform(client);
    int       code = esp_http_client_get_status_code(client);
    esp_http_client_cleanup(client);

    if (err != ESP_OK || code / 100 != 2) {
        ESP_LOGW(TAG, "GET failed err=%s status=%d", esp_err_to_name(err), code);
        free(buf);
        return ESP_FAIL;
    }

    cJSON *root = cJSON_Parse(buf);
    free(buf);
    if (!root) return ESP_ERR_INVALID_RESPONSE;

    const cJSON *upd = cJSON_GetObjectItemCaseSensitive(root, "updated_at");
    if (cJSON_IsString(upd)) {
        strncpy(out->updated_at, upd->valuestring, sizeof(out->updated_at) - 1);
    }
    out->stale = cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(root, "stale"));

    const cJSON *claude = cJSON_GetObjectItemCaseSensitive(root, "claude");
    if (!cJSON_IsObject(claude)) {
        cJSON_Delete(root);
        return ESP_ERR_INVALID_RESPONSE;
    }

    const cJSON *ab = cJSON_GetObjectItemCaseSensitive(claude, "active_block");
    if (cJSON_IsObject(ab)) {
        out->active_block.valid = true;
        const cJSON *t = cJSON_GetObjectItemCaseSensitive(ab, "tokens_used");
        const cJSON *c = cJSON_GetObjectItemCaseSensitive(ab, "cost_usd");
        const cJSON *m = cJSON_GetObjectItemCaseSensitive(ab, "minutes_remaining");
        const cJSON *p = cJSON_GetObjectItemCaseSensitive(ab, "percent_used");
        out->active_block.tokens_used       = cJSON_IsNumber(t) ? (int64_t) t->valuedouble : 0;
        out->active_block.cost_usd          = cJSON_IsNumber(c) ? c->valuedouble : 0.0;
        out->active_block.minutes_remaining = cJSON_IsNumber(m) ? (int32_t) m->valueint : 0;
        out->active_block.percent_used_x100 = pct_x100(p);
    }

    parse_bucket(cJSON_GetObjectItemCaseSensitive(claude, "weekly"),   &out->weekly);
    parse_bucket(cJSON_GetObjectItemCaseSensitive(claude, "today"),    &out->today);
    parse_bucket(cJSON_GetObjectItemCaseSensitive(claude, "month"),    &out->month);
    parse_bucket(cJSON_GetObjectItemCaseSensitive(claude, "lifetime"), &out->lifetime);

    const cJSON *bm = cJSON_GetObjectItemCaseSensitive(claude, "by_model");
    if (cJSON_IsArray(bm)) {
        int n = cJSON_GetArraySize(bm);
        if (n > USAGE_MAX_MODELS) n = USAGE_MAX_MODELS;
        for (int i = 0; i < n; ++i) {
            const cJSON *m    = cJSON_GetArrayItem(bm, i);
            const cJSON *name = cJSON_GetObjectItemCaseSensitive(m, "model");
            const cJSON *tok  = cJSON_GetObjectItemCaseSensitive(m, "tokens");
            const cJSON *cst  = cJSON_GetObjectItemCaseSensitive(m, "cost_usd");
            if (cJSON_IsString(name)) {
                strncpy(out->models[i].model, name->valuestring, sizeof(out->models[i].model) - 1);
            }
            out->models[i].tokens   = cJSON_IsNumber(tok) ? (int64_t) tok->valuedouble : 0;
            out->models[i].cost_usd = cJSON_IsNumber(cst) ? cst->valuedouble : 0.0;
        }
        out->model_count = n;
    }

    // claude.limits — real 5h/7d utilization (0..1 -> x100)
    out->limits.util_5h_x100 = -1;
    out->limits.util_7d_x100 = -1;
    out->limits.reset_5h_min = out->active_block.valid ? out->active_block.minutes_remaining : -1;
    strncpy(out->limits.status, "n/a", sizeof(out->limits.status) - 1);
    const cJSON *lim = cJSON_GetObjectItemCaseSensitive(claude, "limits");
    if (cJSON_IsObject(lim)) {
        const cJSON *u5 = cJSON_GetObjectItemCaseSensitive(lim, "util_5h");
        const cJSON *u7 = cJSON_GetObjectItemCaseSensitive(lim, "util_7d");
        const cJSON *st = cJSON_GetObjectItemCaseSensitive(lim, "status");
        const cJSON *rm = cJSON_GetObjectItemCaseSensitive(lim, "reset_5h_min");
        if (cJSON_IsNumber(u5)) out->limits.util_5h_x100 = (int32_t)(u5->valuedouble * 100.0 + 0.5);
        if (cJSON_IsNumber(u7)) out->limits.util_7d_x100 = (int32_t)(u7->valuedouble * 100.0 + 0.5);
        if (cJSON_IsNumber(rm)) out->limits.reset_5h_min = (int32_t) rm->valueint;  // real unified reset
        if (cJSON_IsString(st)) strncpy(out->limits.status, st->valuestring, sizeof(out->limits.status) - 1);
    }

    // weather (top-level)
    const cJSON *w = cJSON_GetObjectItemCaseSensitive(root, "weather");
    if (cJSON_IsObject(w)) {
        const cJSON *t  = cJSON_GetObjectItemCaseSensitive(w, "temp_c");
        const cJSON *cd = cJSON_GetObjectItemCaseSensitive(w, "condition");
        const cJSON *ic = cJSON_GetObjectItemCaseSensitive(w, "icon");
        const cJSON *cy = cJSON_GetObjectItemCaseSensitive(w, "city");
        out->weather.temp_c = cJSON_IsNumber(t) ? t->valuedouble : 0.0;
        if (cJSON_IsString(cd)) strncpy(out->weather.condition, cd->valuestring, sizeof(out->weather.condition) - 1);
        if (cJSON_IsString(ic)) strncpy(out->weather.icon,      ic->valuestring, sizeof(out->weather.icon) - 1);
        if (cJSON_IsString(cy)) strncpy(out->weather.city,      cy->valuestring, sizeof(out->weather.city) - 1);
        out->weather.valid = cJSON_IsNumber(t);
    }

    // deepseek (top-level)
    const cJSON *ds = cJSON_GetObjectItemCaseSensitive(root, "deepseek");
    if (cJSON_IsObject(ds)) {
        const cJSON *bal = cJSON_GetObjectItemCaseSensitive(ds, "balance");
        const cJSON *cur = cJSON_GetObjectItemCaseSensitive(ds, "currency");
        const cJSON *gr  = cJSON_GetObjectItemCaseSensitive(ds, "granted");
        const cJSON *tp  = cJSON_GetObjectItemCaseSensitive(ds, "topped");
        const cJSON *tk  = cJSON_GetObjectItemCaseSensitive(ds, "today_tokens");
        out->deepseek.balance = cJSON_IsNumber(bal) ? bal->valuedouble : 0.0;
        out->deepseek.granted = cJSON_IsNumber(gr) ? gr->valuedouble : 0.0;
        out->deepseek.topped  = cJSON_IsNumber(tp) ? tp->valuedouble : 0.0;
        out->deepseek.today_tokens = cJSON_IsNumber(tk) ? (int64_t) tk->valuedouble : 0;
        if (cJSON_IsString(cur)) strncpy(out->deepseek.currency, cur->valuestring, sizeof(out->deepseek.currency) - 1);
        else strncpy(out->deepseek.currency, "CNY", sizeof(out->deepseek.currency) - 1);
        out->deepseek.valid = cJSON_IsNumber(bal);
    }

    cJSON_Delete(root);
    return ESP_OK;
}

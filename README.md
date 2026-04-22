# shadowrocket-autorules

Этот репозиторий содержит автоматически обновляемые правила маршрутизации split routing для [**Shadowrocket**](https://apps.apple.com/us/app/shadowrocket/id932747118), собранные на основе данных из [@runetfreedom/russia-v2ray-rules-dat](https://github.com/runetfreedom/russia-v2ray-rules-dat).

Upstream-репозиторий распространяет `geoip.dat` и `geosite.dat`, которые Shadowrocket нативно не понимает. Здесь они распаковываются через [@urlesistiana/v2dat](https://github.com/urlesistiana/v2dat) и конвертируются в `.list` формат, подключаемый в Shadowrocket как `RULE-SET` по URL.

Репозиторий пересобирается в течение часа после обновления upstream.

## Какие категории доступны

Полный список с количеством правил в каждой - [`INDEX.md`](https://github.com/x-netloc/shadowrocket-autorules/blob/dist/INDEX.md).

Описания категорий - в [README апстрима](https://github.com/runetfreedom/russia-v2ray-rules-dat#какие-категории-содержатся-в-файлах). Набор собираемых категорий задается в [`categories.txt`](categories.txt).

## Prebuilt конфиги

Готовые `.conf` файлы импортируются в Shadowrocket целиком: `Config -> Add Config -> URL`.

| Конфиг | Описание | URL для импорта |
| --- | --- | --- |
| [`configs/bypass-blacklist.conf`](configs/bypass-blacklist.conf) | минимум для жизни: через прокси идет только заблокированное в РФ и популярные сервисы (YouTube, OpenAI, Discord, Telegram, Meta, Twitter, Cloudflare, Cloudfront, Fastly), остальное - напрямую | `https://cdn.jsdelivr.net/gh/x-netloc/shadowrocket-autorules@main/configs/bypass-blacklist.conf` |
| [`configs/freedom-no-ru.conf`](configs/freedom-no-ru.conf) | все через прокси, напрямую идет весь RU-трафик | `https://cdn.jsdelivr.net/gh/x-netloc/shadowrocket-autorules@main/configs/freedom-no-ru.conf` |
| [`configs/freedom-no-ru-no-ads.conf`](configs/freedom-no-ru-no-ads.conf) | то же, что `freedom-no-ru`, плюс блокировка рекламы (`category-ads-all`) | `https://cdn.jsdelivr.net/gh/x-netloc/shadowrocket-autorules@main/configs/freedom-no-ru-no-ads.conf` |

## Подключить правила вручную

Вы можете собрать кастомный ruleset на свое усмотрение. Каждый `.list` можно подключить отдельной строкой в `[Rule]`:

```
RULE-SET,https://cdn.jsdelivr.net/gh/x-netloc/shadowrocket-autorules@dist/geosite/ru-blocked.list,PROXY
RULE-SET,https://cdn.jsdelivr.net/gh/x-netloc/shadowrocket-autorules@dist/geoip/ru-blocked.list,PROXY,no-resolve
```

Шаблон URL:

- через jsDelivr (кэш ~12 часов): `https://cdn.jsdelivr.net/gh/x-netloc/shadowrocket-autorules@dist/<kind>/<category>.list`
- напрямую с GitHub: `https://raw.githubusercontent.com/x-netloc/shadowrocket-autorules/dist/<kind>/<category>.list`

## Ограничения

Shadowrocket не поддерживает regex по домену, поэтому `regexp:` записи из апстрима при конвертации пропускаются. `domain:`, `full:`, `keyword:` и CIDR v4/v6 конвертируются один в один.

## Благодарности

- [@runetfreedom/russia-v2ray-rules-dat](https://github.com/runetfreedom/russia-v2ray-rules-dat) - источник данных
- [@urlesistiana/v2dat](https://github.com/urlesistiana/v2dat) - распаковка `.dat` файлов

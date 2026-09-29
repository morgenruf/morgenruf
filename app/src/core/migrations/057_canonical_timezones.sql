-- Rewrite legacy timezone names to their canonical IANA names.
--
-- Chrome's Intl API reports some zones by their old names (Asia/Calcutta),
-- and the dashboard saved them as sent. Debian no longer ships those names in
-- its system tz database, so APScheduler could not resolve them and the
-- schedule never fired (standup_schedules row 38, 2026-09-29). The app now
-- installs the tzdata package and canonicalises names on save; this rewrites
-- the rows already stored.
--
-- Keep the list in step with LEGACY_TZ_ALIASES in src/core/timezones.py;
-- tests/test_timezones.py compares the two. Module tables are updated only
-- when they exist, so a deployment without a module still migrates. The
-- migration runner applies each file in one transaction, which is when the
-- lookup table below goes away.

CREATE TEMP TABLE tz_legacy_aliases (
    legacy TEXT PRIMARY KEY,
    canonical TEXT NOT NULL
) ON COMMIT DROP;

INSERT INTO tz_legacy_aliases (legacy, canonical) VALUES
    ('Asia/Calcutta', 'Asia/Kolkata'),
    ('Asia/Saigon', 'Asia/Ho_Chi_Minh'),
    ('Asia/Katmandu', 'Asia/Kathmandu'),
    ('Asia/Rangoon', 'Asia/Yangon'),
    ('Asia/Dacca', 'Asia/Dhaka'),
    ('Asia/Thimbu', 'Asia/Thimphu'),
    ('Asia/Ujung_Pandang', 'Asia/Makassar'),
    ('Asia/Ulan_Bator', 'Asia/Ulaanbaatar'),
    ('Asia/Macao', 'Asia/Macau'),
    ('Asia/Chongqing', 'Asia/Shanghai'),
    ('Asia/Chungking', 'Asia/Shanghai'),
    ('Asia/Harbin', 'Asia/Shanghai'),
    ('Asia/Tel_Aviv', 'Asia/Jerusalem'),
    ('Asia/Istanbul', 'Europe/Istanbul'),
    ('Europe/Kiev', 'Europe/Kyiv'),
    ('Europe/Uzhgorod', 'Europe/Kyiv'),
    ('Europe/Zaporozhye', 'Europe/Kyiv'),
    ('Europe/Belfast', 'Europe/London'),
    ('Europe/Nicosia', 'Asia/Nicosia'),
    ('Africa/Asmera', 'Africa/Asmara'),
    ('Africa/Timbuktu', 'Africa/Bamako'),
    ('Atlantic/Faeroe', 'Atlantic/Faroe'),
    ('Pacific/Truk', 'Pacific/Chuuk'),
    ('Pacific/Yap', 'Pacific/Chuuk'),
    ('Pacific/Ponape', 'Pacific/Pohnpei'),
    ('Pacific/Enderbury', 'Pacific/Kanton'),
    ('Pacific/Samoa', 'Pacific/Pago_Pago'),
    ('America/Buenos_Aires', 'America/Argentina/Buenos_Aires'),
    ('America/Catamarca', 'America/Argentina/Catamarca'),
    ('America/Cordoba', 'America/Argentina/Cordoba'),
    ('America/Jujuy', 'America/Argentina/Jujuy'),
    ('America/Mendoza', 'America/Argentina/Mendoza'),
    ('America/Indianapolis', 'America/Indiana/Indianapolis'),
    ('America/Fort_Wayne', 'America/Indiana/Indianapolis'),
    ('America/Knox_IN', 'America/Indiana/Knox'),
    ('America/Louisville', 'America/Kentucky/Louisville'),
    ('America/Godthab', 'America/Nuuk'),
    ('America/Montreal', 'America/Toronto'),
    ('America/Nipigon', 'America/Toronto'),
    ('America/Thunder_Bay', 'America/Toronto'),
    ('America/Rainy_River', 'America/Winnipeg'),
    ('America/Yellowknife', 'America/Edmonton'),
    ('America/Pangnirtung', 'America/Iqaluit'),
    ('America/Shiprock', 'America/Denver'),
    ('America/Ensenada', 'America/Tijuana'),
    ('America/Santa_Isabel', 'America/Tijuana'),
    ('America/Porto_Acre', 'America/Rio_Branco'),
    ('Australia/Currie', 'Australia/Hobart'),
    ('US/Eastern', 'America/New_York'),
    ('US/Central', 'America/Chicago'),
    ('US/Mountain', 'America/Denver'),
    ('US/Pacific', 'America/Los_Angeles'),
    ('US/Alaska', 'America/Anchorage'),
    ('US/Hawaii', 'Pacific/Honolulu'),
    ('US/Arizona', 'America/Phoenix'),
    ('US/East-Indiana', 'America/Indiana/Indianapolis'),
    ('US/Indiana-Starke', 'America/Indiana/Knox'),
    ('US/Michigan', 'America/Detroit'),
    ('US/Aleutian', 'America/Adak'),
    ('US/Samoa', 'Pacific/Pago_Pago'),
    ('Canada/Atlantic', 'America/Halifax'),
    ('Canada/Central', 'America/Winnipeg'),
    ('Canada/Eastern', 'America/Toronto'),
    ('Canada/Mountain', 'America/Edmonton'),
    ('Canada/Newfoundland', 'America/St_Johns'),
    ('Canada/Pacific', 'America/Vancouver'),
    ('Canada/Saskatchewan', 'America/Regina'),
    ('Brazil/East', 'America/Sao_Paulo'),
    ('Mexico/General', 'America/Mexico_City'),
    ('GB', 'Europe/London'),
    ('Eire', 'Europe/Dublin'),
    ('Poland', 'Europe/Warsaw'),
    ('Portugal', 'Europe/Lisbon'),
    ('Turkey', 'Europe/Istanbul'),
    ('Egypt', 'Africa/Cairo'),
    ('Iran', 'Asia/Tehran'),
    ('Israel', 'Asia/Jerusalem'),
    ('Japan', 'Asia/Tokyo'),
    ('PRC', 'Asia/Shanghai'),
    ('ROC', 'Asia/Taipei'),
    ('ROK', 'Asia/Seoul'),
    ('Hongkong', 'Asia/Hong_Kong'),
    ('Singapore', 'Asia/Singapore'),
    ('NZ', 'Pacific/Auckland'),
    ('UCT', 'Etc/UTC'),
    ('Universal', 'Etc/UTC'),
    ('Zulu', 'Etc/UTC'),
    ('Etc/UCT', 'Etc/UTC'),
    ('Etc/Universal', 'Etc/UTC'),
    ('Etc/Zulu', 'Etc/UTC');

DO $$
DECLARE
    target RECORD;
BEGIN
    FOR target IN
        SELECT * FROM (VALUES
            ('workspace_config', 'schedule_tz'),
            ('members', 'tz'),
            ('standup_schedules', 'schedule_tz'),
            ('connect_programs', 'timezone'),
            ('celebration_settings', 'timezone')
        ) AS t (tbl, col)
    LOOP
        IF to_regclass(target.tbl) IS NOT NULL THEN
            EXECUTE format(
                'UPDATE %1$I SET %2$I = a.canonical FROM tz_legacy_aliases a WHERE %1$I.%2$I = a.legacy',
                target.tbl,
                target.col
            );
        END IF;
    END LOOP;
END
$$;

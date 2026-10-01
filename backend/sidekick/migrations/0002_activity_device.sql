-- Device provenance for activities; used to detect watch changes (baseline discontinuities).
ALTER TABLE activity ADD COLUMN device_id TEXT;
ALTER TABLE activity ADD COLUMN manufacturer TEXT;
UPDATE activity SET
    device_id = (SELECT CAST(json_extract(r.payload_json, '$.deviceId') AS TEXT) FROM raw_payload r
                 WHERE r.source = activity.source AND r.kind = 'activity_summary' AND r.source_key = activity.source_id),
    manufacturer = (SELECT json_extract(r.payload_json, '$.manufacturer') FROM raw_payload r
                    WHERE r.source = activity.source AND r.kind = 'activity_summary' AND r.source_key = activity.source_id);

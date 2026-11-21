INSERT INTO worker.patient_context (patient_id, kind, ts, text) VALUES
    ('p-001', 'profile',    NULL,                   '54 y, female, hypertension'),
    ('p-001', 'medication', '2026-01-10 09:00+00',  'ramipril 5 mg daily'),
    ('p-001', 'diary',      '2026-03-13 21:30+00',  'got my flu shot this morning, arm is sore'),
    ('p-001', 'diary',      '2026-03-16 08:00+00',  'feeling fine again'),
    ('p-002', 'profile',    NULL,                   '67 y, male, COPD'),
    ('p-002', 'encounter',  '2026-03-02 10:00+00',  'GP visit, stable'),
    ('p-002', 'diary',      '2026-03-14 22:10+00',  'short of breath on the stairs'),
    ('p-003', 'profile',    NULL,                   '41 y, female, no known conditions'),
    ('p-003', 'diary',      '2026-03-14 19:00+00',  'ran a half marathon today');

INSERT INTO worker.suspicious_events (patient_id, night_date, reasons, red_flag, features) VALUES
    ('p-001', '2026-03-14', 'rule:multi_signal', false, '{"rhr_z": 2.4, "temp_z": 1.9}'),
    ('p-001', '2026-03-15', 'ml:0.82',           false, '{"rhr_z": 1.6, "hrv_z": -1.8}'),
    ('p-002', '2026-03-14', 'rule:spo2_floor',   true,  '{"spo2_min": 84, "spo2_pct_lt90": 12.5}'),
    ('p-002', '2026-03-15', 'rule:trend',        false, '{"rr_z": 2.1}'),
    ('p-003', '2026-03-14', 'rule:multi_signal', false, '{"rhr_z": 2.9, "hrv_z": -2.2}')
ON CONFLICT (patient_id, night_date) DO NOTHING;

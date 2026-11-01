from __future__ import annotations


DOCS: list[dict] = [
    {
        "id": "DOC-K2",
        "filename": "REX-K2_Service_Manual_DEMO.txt",
        "title": "REX-K2 Service Manual (DEMO)",
        "doc_type": "service_manual",
        "version": "2026.10-DEMO",
        "model": "K2",
    },
    {
        "id": "DOC-H1",
        "filename": "REX-H1_Service_Manual_DEMO.txt",
        "title": "REX-H1 Service Manual (DEMO)",
        "doc_type": "service_manual",
        "version": "2026.10-DEMO",
        "model": "H1",
    },
    {
        "id": "DOC-A3",
        "filename": "REX-A3_Service_Manual_DEMO.txt",
        "title": "REX-A3 Service Manual (DEMO)",
        "doc_type": "service_manual",
        "version": "2026.10-DEMO",
        "model": "A3",
    },
    {
        "id": "DOC-SAFE",
        "filename": "Safety_and_Escalation_Guide_DEMO.txt",
        "title": "Safety and Escalation Guide (DEMO)",
        "doc_type": "safety_guide",
        "version": "2026.10-DEMO",
        "model": "ALL",
    },
]


CHUNKS: list[dict] = [
    {
        "doc_id": "DOC-SAFE",
        "model": "ALL",
        "page": 1,
        "section": "Safety escalation",
        "keywords": "fall locked joint smoke fire injury emergency stop use support escalation",
        "text": (
            "Safety escalation. If a patient falls, a joint locks, the device loses power suddenly, "
            "the device smokes or becomes unusually hot, or anyone is injured, stop using the device. "
            "Support the limb, keep the patient in a safe position, and do not force or disassemble the joint. "
            "If there is pain, injury, loss of consciousness, smoke, fire, or an electric-shock concern, "
            "contact local emergency services or a clinician first. Escalate the ticket to senior support."
        ),
    },
    {
        "doc_id": "DOC-SAFE",
        "model": "ALL",
        "page": 2,
        "section": "Remote support boundary",
        "keywords": "remote support diagnosis clinical medical advice safety boundary escalation",
        "text": (
            "Remote support boundary. Support agents may explain approved cleaning, charging, pairing, "
            "firmware, and calibration steps from the current service manual. They must not diagnose a "
            "medical condition, promise a clinical outcome, or tell a customer to continue using a device "
            "after a safety event. When evidence is incomplete, ask for the model, serial number, error code, "
            "and a short description of what happened, then route the case for specialist review."
        ),
    },
    {
        "doc_id": "DOC-K2",
        "model": "K2",
        "page": 3,
        "section": "Intended use and pre-session check",
        "keywords": "intended use supervised clinician fit battery strap pre-session",
        "text": (
            "The REX-K2 is a supervised knee rehabilitation exoskeleton. It is not intended for unsupervised "
            "walking or as a mobility substitute. Before each session, confirm the fit, charge level, strap "
            "position, and clinician-approved settings. Check that the knee joint moves freely while the device "
            "is powered off and that no liner is folded under the strap."
        ),
    },
    {
        "doc_id": "DOC-K2",
        "model": "K2",
        "page": 6,
        "section": "Battery and charging",
        "keywords": "battery charging charger charging port hot temperature 2.5 3 hours",
        "text": (
            "Use only the supplied REX-K2 charger. A normal charge takes approximately 2.5 to 3 hours. "
            "Charge in a dry, ventilated area between 10 and 30 degrees Celsius. Do not charge if the charging "
            "port is wet, damaged, or hot to the touch. Stop charging and contact support if the port becomes "
            "very hot, the cable is damaged, or there is an odor. Do not open the battery enclosure."
        ),
    },
    {
        "doc_id": "DOC-K2",
        "model": "K2",
        "page": 9,
        "section": "Firmware update",
        "keywords": "firmware update REX Care app bluetooth charger restart version",
        "text": (
            "Use the REX Care app version 3.0 or later for firmware updates. Connect the device to its charger, "
            "enable Bluetooth, and keep the app in the foreground. Start the update and do not power off the "
            "device until the app reports completion. After the update, restart the device and verify the version "
            "in Settings. If the update fails, reconnect and retry once; if it fails again, collect the app log "
            "and contact support."
        ),
    },
    {
        "doc_id": "DOC-K2",
        "model": "K2",
        "page": 11,
        "section": "Remote control pairing",
        "keywords": "remote control pairing bluetooth LED reset power cycle",
        "text": (
            "To pair the remote control, power on the remote and hold the pairing button for two seconds until "
            "the LED flashes blue. Select Pair Remote in the REX Care app. If pairing does not complete within "
            "60 seconds, close the app, power-cycle the remote, and retry once. Do not press the pairing button "
            "repeatedly during the connection attempt."
        ),
    },
    {
        "doc_id": "DOC-K2",
        "model": "K2",
        "page": 14,
        "section": "Knee joint calibration",
        "keywords": "knee joint calibration range seated no load unlock",
        "text": (
            "Calibrate the knee joint while the patient is seated, the limb is supported, and no load is applied. "
            "Unlock the joint, open Calibration in the REX Care app, and follow the on-screen range-of-motion "
            "prompt. Do not force the joint beyond its comfortable range. If calibration reports a range error, "
            "stop and contact support rather than repeating it several times."
        ),
    },
    {
        "doc_id": "DOC-K2",
        "model": "K2",
        "page": 18,
        "section": "Error E-12",
        "keywords": "error code E-12 motor assist timeout stop session joint movement battery log",
        "text": (
            "E-12 indicates a motor-assist timeout. Stop the session and remove the load. Check that the knee "
            "joint moves freely while powered off and confirm the battery level. Record the error code, session "
            "time, and firmware version in the ticket. If E-12 recurs, contact support for a remote log review. "
            "Do not disassemble the actuator or continue the session."
        ),
    },
    {
        "doc_id": "DOC-K2",
        "model": "K2",
        "page": 21,
        "section": "Clicking noise",
        "keywords": "clicking noise abnormal sound strap liner alignment resistance",
        "text": (
            "Intermittent clicking can come from a loose strap, a folded liner, or an alignment issue. Ask the "
            "customer to stop the session and inspect the strap and liner with the device powered off. If the "
            "clicking continues with resistance or is accompanied by E-12, stop use and collect a short video, "
            "the error log, and the serial number for review. Do not continue a session with a repeated clicking "
            "noise and reduced assistance."
        ),
    },
    {
        "doc_id": "DOC-K2",
        "model": "K2",
        "page": 24,
        "section": "Cleaning and storage",
        "keywords": "cleaning liner strap mild soap disinfectant dry storage",
        "text": (
            "Wipe the liner with a damp cloth and mild soap. Use only an approved disinfectant for shared devices "
            "and follow the facility protocol. Do not immerse the actuator, battery, or charging port in water. "
            "Hand-wash removable straps, rinse thoroughly, and allow them to air-dry completely before reattaching. "
            "Store the device powered off, dry, and within the temperature range in the specifications."
        ),
    },
    {
        "doc_id": "DOC-K2",
        "model": "K2",
        "page": 27,
        "section": "Warranty and recall",
        "keywords": "warranty recall serial number 24 months frame 12 months battery",
        "text": (
            "The demo warranty policy covers the frame for 24 months and the battery for 12 months from delivery. "
            "A serial number is required for verification. If the device is in a recall or service campaign, stop "
            "routine use and follow the campaign instructions. Do not promise a replacement or refund until the "
            "serial number and warranty status have been checked."
        ),
    },
    {
        "doc_id": "DOC-K2",
        "model": "K2",
        "page": 30,
        "section": "Locked joint safety flow",
        "keywords": "locked joint support limb do not force safety event escalate",
        "text": (
            "If the knee joint remains locked, stop the session, support the limb, and keep the patient seated or "
            "in a safe position. Do not force the joint, manually override the actuator, or remove the cover. "
            "Treat the event as a safety escalation and ask whether the patient fell, has pain, or is injured. "
            "Medical concerns should be directed to a clinician or emergency service."
        ),
    },
    {
        "doc_id": "DOC-H1",
        "model": "H1",
        "page": 3,
        "section": "Intended use and fit",
        "keywords": "intended use supervised hip fit strap clinician",
        "text": (
            "The REX-H1 is a supervised hip-assist exoskeleton for rehabilitation sessions. Confirm the pelvic "
            "strap, thigh cuff, and battery before use. The device is not a substitute for clinical assessment or "
            "unsupervised mobility."
        ),
    },
    {
        "doc_id": "DOC-H1",
        "model": "H1",
        "page": 7,
        "section": "Battery and charging",
        "keywords": "battery charging time charger hot warranty",
        "text": (
            "The H1 battery normally reaches full charge in about 2 hours with the supplied charger. Use a dry, "
            "ventilated area. Do not charge a device with a damaged cable, wet port, or unusually hot housing. "
            "For a hot charging port, stop charging and create a safety review before further use."
        ),
    },
    {
        "doc_id": "DOC-H1",
        "model": "H1",
        "page": 10,
        "section": "Firmware and app",
        "keywords": "firmware update app bluetooth version restart",
        "text": (
            "Update H1 firmware through the REX Care app. Keep the device on the charger and the app in the "
            "foreground. After the update, restart the device and confirm the version. If the update does not "
            "complete, retry once and collect the app log if it fails again."
        ),
    },
    {
        "doc_id": "DOC-H1",
        "model": "H1",
        "page": 13,
        "section": "Remote pairing",
        "keywords": "remote control pairing bluetooth reset LED",
        "text": (
            "Power-cycle the remote, open Pair Remote in the app, and hold the pairing button for two seconds. "
            "Allow up to 60 seconds for the connection. If pairing still fails, confirm the app version and "
            "Bluetooth permissions before collecting a log."
        ),
    },
    {
        "doc_id": "DOC-H1",
        "model": "H1",
        "page": 16,
        "section": "Hip alignment",
        "keywords": "hip alignment pelvic strap thigh cuff calibration",
        "text": (
            "Check that the pelvic strap is centered and the thigh cuff is not twisted. Perform alignment while "
            "the patient is seated and the device is powered off. If the hip joint feels forced or the alignment "
            "cannot be completed comfortably, stop and contact support."
        ),
    },
    {
        "doc_id": "DOC-H1",
        "model": "H1",
        "page": 19,
        "section": "Error E-21",
        "keywords": "error code E-21 hip motor sensor",
        "text": (
            "E-21 indicates an intermittent hip sensor signal. Stop the session, check the cable and connector "
            "for visible damage, and record the code and firmware version. Do not open the control box. Repeated "
            "E-21 events require a support log review and possible service."
        ),
    },
    {
        "doc_id": "DOC-H1",
        "model": "H1",
        "page": 22,
        "section": "Cleaning and warranty",
        "keywords": "cleaning hip liner strap warranty frame battery",
        "text": (
            "Wipe the H1 liner with a damp cloth and approved disinfectant. Remove and air-dry straps. The demo "
            "warranty covers the frame for 24 months and the battery for 12 months. Verify the serial number and "
            "recall status before discussing a replacement."
        ),
    },
    {
        "doc_id": "DOC-A3",
        "model": "A3",
        "page": 4,
        "section": "Intended use and fit",
        "keywords": "intended use ankle fit clinician supervised",
        "text": (
            "The REX-A3 is a supervised ankle-mobility exoskeleton. Confirm the foot plate, ankle cuff, and "
            "battery before use. Do not use the device as a stand-alone walking aid."
        ),
    },
    {
        "doc_id": "DOC-A3",
        "model": "A3",
        "page": 8,
        "section": "Battery and charging",
        "keywords": "battery charging charger port hot temperature",
        "text": (
            "Use only the supplied A3 charger. A full charge normally takes 2 to 2.5 hours. Stop charging if the "
            "port or battery housing becomes very hot, the cable is damaged, or there is an unusual odor. Do not "
            "cover the charger during use and do not open the battery enclosure."
        ),
    },
    {
        "doc_id": "DOC-A3",
        "model": "A3",
        "page": 11,
        "section": "Firmware update",
        "keywords": "firmware update app bluetooth charger restart",
        "text": (
            "Update A3 firmware in the REX Care app while the device is on the charger. Keep the app open and "
            "wait for the completion message. Restart the device and verify the firmware version. If the update "
            "fails, retry once and collect the app log."
        ),
    },
    {
        "doc_id": "DOC-A3",
        "model": "A3",
        "page": 14,
        "section": "Ankle calibration",
        "keywords": "ankle calibration range seated no load",
        "text": (
            "Calibrate the ankle while the patient is seated, the foot is supported, and no load is applied. "
            "Follow the range prompt in the app and stop if the ankle is uncomfortable. Do not force the joint "
            "through a restricted range."
        ),
    },
    {
        "doc_id": "DOC-A3",
        "model": "A3",
        "page": 17,
        "section": "Error E-31",
        "keywords": "error code E-31 ankle sensor motor",
        "text": (
            "E-31 indicates an ankle sensor timeout. Stop the session, check the ankle cable connection, and "
            "record the error log. Do not continue the session or disassemble the ankle module. Repeated events "
            "require support review."
        ),
    },
    {
        "doc_id": "DOC-A3",
        "model": "A3",
        "page": 20,
        "section": "Hot charging port",
        "keywords": "charging port hot stop charging safety smoke fire",
        "text": (
            "If the charging port is hot, unplug the charger and let the device cool in a ventilated area. Do not "
            "touch a damaged port or continue charging. If there is smoke, odor, swelling, or a burning smell, "
            "treat it as a safety event and escalate immediately."
        ),
    },
    {
        "doc_id": "DOC-A3",
        "model": "A3",
        "page": 23,
        "section": "Cleaning and warranty",
        "keywords": "cleaning ankle liner strap warranty",
        "text": (
            "Clean the foot plate and liner with a damp cloth and approved disinfectant. Do not immerse the "
            "ankle module. The demo warranty covers the frame for 24 months and the battery for 12 months. "
            "Check the serial number and recall status before any replacement discussion."
        ),
    },
]


# Codebook — Eurobarometer ZA8841, read from the source file

*Generated 2026-08-08 by `scripts/export_codebook.py`, directly from
the binary `.sav`. Nothing here is transcribed by hand.*

## Why this document exists

`ZA8841_v1-0-0.sav` is a **binary SPSS file**. Opened in a text editor it shows
only this much readable text before turning to packed bytes:

```
$FL2  @(#) IBM SPSS STATISTICS 64-bit MS Windows 29.0.1.0
```

Every answer inside it is a **numeric code**. `qc7_1 = 2` means nothing until the
file's own label dictionary says that 2 is *"2 - 3 days"*. This document extracts
that dictionary so the contents can be read, checked against GESIS's published
codebook, and audited independently of any code in this project.

## File identity

| | |
|---|---|
| File | `ZA8841_v1-0-0.sav` |
| Study | Eurobarometer 101.1 / Special Eurobarometer 547 |
| DOI | `10.4232/1.14461` |
| Produced by | `@(#) IBM SPSS STATISTICS 64-bit MS Windows 29.0.1.0` |
| File created | 2025-03-10 13:29:15 |
| Encoding | UTF-8 |
| Rows (respondents) | **26,405** |
| Columns (variables) | **668** |
| Variable labels | 668 |
| Value-label sets | 639 |

The row and column counts are asserted by `scripts/run_pipeline.py` before anything
runs: a different file or survey wave stops the pipeline rather than producing
plausible numbers about the wrong data.

## Coverage

**28 territories, 26,405 respondents.** Germany is split East/West at source and is collapsed to `DE` during cleaning.

AT 1,010 · BE 1,047 · BG 1,034 · CY 500 · CZ 1,011 · DE-E 482 · DE-W 1,039 · DK 1,003 · EE 1,007 · ES 1,002 · FI 1,024 · FR 1,012 · GR 1,002 · HR 1,001 · HU 1,019 · IE 1,001 · IT 1,025 · LT 1,002 · LU 506 · LV 1,008 · MT 506 · NL 1,022 · PL 1,019 · PT 1,031 · RO 1,046 · SE 1,036 · SI 1,002 · SK 1,008


## The variables this project uses

Every one shown with the label and the code list **as stored in the file**.

### Resilience horizon (RHI)

| variable   | label in the file                                                | codes                                                                                                                                        |
|:-----------|:-----------------------------------------------------------------|:---------------------------------------------------------------------------------------------------------------------------------------------|
| `qc7_1`    | HOW MANY DAYS MEET WATER NEEDS IF WATER SERVICES DISRUPTED       | `1` 1 day or less · `2` 2 - 3 days · `3` 4 - 7 days · `4` More than 7 days · `5` Not applicable (SPONTANEOUS) · `6` Don't know (SPONTANEOUS) |
| `qc7_2`    | HOW MANY DAYS POWER ESSENT APPLIANCES IF ELEC INTERRUPTED        | `1` 1 day or less · `2` 2 - 3 days · `3` 4 - 7 days · `4` More than 7 days · `5` Not applicable (SPONTANEOUS) · `6` Don't know (SPONTANEOUS) |
| `qc7_3`    | HOW MANY DAYS COOK MEALS/HEAT IF GAS DISRUPTED                   | `1` 1 day or less · `2` 2 - 3 days · `3` 4 - 7 days · `4` More than 7 days · `5` Not applicable (SPONTANEOUS) · `6` Don't know (SPONTANEOUS) |
| `qc7_4`    | HOW MANY DAYS PROVIDE FOOD IF TRANSPORTATION DISRUPTED           | `1` 1 day or less · `2` 2 - 3 days · `3` 4 - 7 days · `4` More than 7 days · `5` Not applicable (SPONTANEOUS) · `6` Don't know (SPONTANEOUS) |
| `qc7_5`    | HOW MANY DAYS CONTINUED TREATMENT IF MEDICATION SUPPLY DISRUPTED | `1` 1 day or less · `2` 2 - 3 days · `3` 4 - 7 days · `4` More than 7 days · `5` Not applicable (SPONTANEOUS) · `6` Don't know (SPONTANEOUS) |

### Preparedness actions (PGI, PRI)

| variable   | label in the file                                                        | codes                                                                                                                                     |
|:-----------|:-------------------------------------------------------------------------|:------------------------------------------------------------------------------------------------------------------------------------------|
| `qc6.1`    | DISASTER MEASURES IN HH: EMERGENCY SUPPLY DRINKS/FOOD                    | `0` Not mentioned · `1` Keep an emergency supply stock/pack of drinks, food                                                               |
| `qc6.2`    | DISASTER MEASURES IN HH: EMERGENCY SUPPLY WATER COOKING/HYGIENE          | `0` Not mentioned · `1` Keep an emergency supply of water for cooking and hygiene                                                         |
| `qc6.3`    | DISASTER MEASURES IN HH: FLASHLIGHT/CANDLES                              | `0` Not mentioned · `1` Have flashlight or candles accessible                                                                             |
| `qc6.4`    | DISASTER MEASURES IN HH: BATTERY-POWERED RADIO                           | `0` Not mentioned · `1` Have a battery-powered radio accessible                                                                           |
| `qc6.5`    | DISASTER MEASURES IN HH: EMERGENCY PHARMACY                              | `0` Not mentioned · `1` Keep a home pharmacy for emergencies                                                                              |
| `qc6.6`    | DISASTER MEASURES IN HH: COPIES IMP DOCUMENTS/STORED SAFELY              | `0` Not mentioned · `1` Have made sure you have copies of your most important documents or have stored them safely                        |
| `qc6.7`    | DISASTER MEASURES IN HH: EMERGENCY GRAB-BAG                              | `0` Not mentioned · `1` Have prepared a grab-bag, in case you need to evacuate rapidly in an emergency                                    |
| `qc6.8`    | DISASTER MEASURES IN HH: SIGNED UP FOR ALERTS                            | `0` Not mentioned · `1` Have signed up for alerts and warnings from emergency services or authorities                                     |
| `qc6.9`    | DISASTER MEASURES IN HH: PARTICIPATED IN TRAINING/EXERCISE               | `0` Not mentioned · `1` Have participated in a training or exercise, to learn how to react in an emergency                                |
| `qc6.10`   | DISASTER MEASURES IN HH: INFORMED ABOUT OFFICIAL RESPONSE PLAN           | `0` Not mentioned · `1` Got informed on the response plan your city, region or country has for a disaster or emergency (e.g. (...)        |
| `qc6.11`   | DISASTER MEASURES IN HH: AGREED WITH FRIENDS/FAMILY TO CONTACT           | `0` Not mentioned · `1` Agreed with family, friends on how to contact each other in case of an emergency                                  |
| `qc6.12`   | DISASTER MEASURES IN HH: DISCUSSED COMMON PROT MEASURES IN NEIGHBOURHOOD | `0` Not mentioned · `1` Discussed common protective measures in your neighbourhood                                                        |
| `qc6.13`   | DISASTER MEASURES IN HH: INVESTED IN PROT MEASURES IN HOME               | `0` Not mentioned · `1` Have invested in protective measures in your home (e.g. flood-proofed the electricity installation, cleared (...) |
| `qc6.14`   | DISASTER MEASURES IN HH: OTHER                                           | `0` Not mentioned · `1` Other                                                                                                             |
| `qc6.15`   | DISASTER MEASURES IN HH: DK (SPONT)                                      | `0` Not mentioned · `1` Don't know (SPONTANEOUS)                                                                                          |
| `qc6t`     | DISASTER MEASURES IN HH - NUMBER OF MEASURES                             | `1` 1 mention · `2` 2 mentions · `3` 3 mentions · `4` 4 mentions · `5` +5 mentions · `6` Don't know (SPONTANEOUS)                         |

### Information & awareness

| variable   | label in the file                                                                        | codes                                                                                                                                                            |
|:-----------|:-----------------------------------------------------------------------------------------|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `qc5_1`    | STATEMENTS DISASTER RISKS - READ/SEENHEARD INFO IN LAST 12M                              | `1` Totally agree · `2` Tend to agree · `3` Tend to disagree · `4` Totally disagree · `5` It depends on the country (SPONTANEOUS) · `6` Don't know (SPONTANEOUS) |
| `qc5_2`    | STATEMENTS DISASTER RISKS - FEEL WELL INFORMED                                           | `1` Totally agree · `2` Tend to agree · `3` Tend to disagree · `4` Totally disagree · `5` It depends on the country (SPONTANEOUS) · `6` Don't know (SPONTANEOUS) |
| `qc5_3`    | STATEMENTS DISASTER RISKS - TRUST INFORMATION BY PUB AUTH ON RISKS WHERE YOU LIVE        | `1` Totally agree · `2` Tend to agree · `3` Tend to disagree · `4` Totally disagree · `5` It depends on the country (SPONTANEOUS) · `6` Don't know (SPONTANEOUS) |
| `qc5_4`    | STATEMENTS DISASTER RISKS - EASY TO FIND INFORMATION BY PUB AUTH ON RISKS WHERE YOU LIVE | `1` Totally agree · `2` Tend to agree · `3` Tend to disagree · `4` Totally disagree · `5` It depends on the country (SPONTANEOUS) · `6` Don't know (SPONTANEOUS) |
| `qc5_5`    | STATEMENTS DISASTER RISKS - KNOW WHERE TO FIND INFO WHEN TRAVELLING TO OTH EU CNTRY      | `1` Totally agree · `2` Tend to agree · `3` Tend to disagree · `4` Totally disagree · `5` It depends on the country (SPONTANEOUS) · `6` Don't know (SPONTANEOUS) |

### Attitudes & barriers

| variable   | label in the file                                                         | codes                                                                                                                                                                     |
|:-----------|:--------------------------------------------------------------------------|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `qc8_1`    | PERSONAL DISASTER PREPAREDNESS - BETTER ABLE TO COPE BY PREP              | `1` Totally agree · `2` Tend to agree · `3` Tend to disagree · `4` Totally disagree · `5` It depends on the type of disaster (SPONTANEOUS) · `6` Don't know (SPONTANEOUS) |
| `qc8_2`    | PERSONAL DISASTER PREPAREDNESS - FEEL WELL PREPARED                       | `1` Totally agree · `2` Tend to agree · `3` Tend to disagree · `4` Totally disagree · `5` It depends on the type of disaster (SPONTANEOUS) · `6` Don't know (SPONTANEOUS) |
| `qc8_3`    | PERSONAL DISASTER PREPAREDNESS - NO TIME/FIN RESOURCES TO PREP            | `1` Totally agree · `2` Tend to agree · `3` Tend to disagree · `4` Totally disagree · `5` It depends on the type of disaster (SPONTANEOUS) · `6` Don't know (SPONTANEOUS) |
| `qc8_4`    | PERSONAL DISASTER PREPAREDNESS - EASY TO FIND INFO ON HOW TO PREP         | `1` Totally agree · `2` Tend to agree · `3` Tend to disagree · `4` Totally disagree · `5` It depends on the type of disaster (SPONTANEOUS) · `6` Don't know (SPONTANEOUS) |
| `qc8_5`    | PERSONAL DISASTER PREPAREDNESS - NEED MORE INFO TO PREP                   | `1` Totally agree · `2` Tend to agree · `3` Tend to disagree · `4` Totally disagree · `5` It depends on the type of disaster (SPONTANEOUS) · `6` Don't know (SPONTANEOUS) |
| `qc8_6`    | PERSONAL DISASTER PREPAREDNESS - KNOW HOW EMERG SERVICES WILL ALERT       | `1` Totally agree · `2` Tend to agree · `3` Tend to disagree · `4` Totally disagree · `5` It depends on the type of disaster (SPONTANEOUS) · `6` Don't know (SPONTANEOUS) |
| `qc8_7`    | PERSONAL DISASTER PREPAREDNESS - KNOW WHAT TO DO IN EVENT OF DISASTER     | `1` Totally agree · `2` Tend to agree · `3` Tend to disagree · `4` Totally disagree · `5` It depends on the type of disaster (SPONTANEOUS) · `6` Don't know (SPONTANEOUS) |
| `qc8_8`    | PERSONAL DISASTER PREPAREDNESS - EMPLOYER/SCHOOL ENCOURAGES TRAINING/PREP | `1` Totally agree · `2` Tend to agree · `3` Tend to disagree · `4` Totally disagree · `5` It depends on the type of disaster (SPONTANEOUS) · `6` Don't know (SPONTANEOUS) |
| `qc8_9`    | PERSONAL DISASTER PREPAREDNESS - EMERG SERVICES ENCOURAGE TRAINING/PREP   | `1` Totally agree · `2` Tend to agree · `3` Tend to disagree · `4` Totally disagree · `5` It depends on the type of disaster (SPONTANEOUS) · `6` Don't know (SPONTANEOUS) |

### Demographics

| variable   | label in the file                      | codes                                                                                                                                                                                                                                                                  |
|:-----------|:---------------------------------------|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `d10`      | GENDER                                 | `1` Man · `2` Woman · `3` None of the above/ Non binary/ do not recognize yourself in above categories/Prefer not to say                                                                                                                                               |
| `d11`      | AGE EXACT                              | `15` 15 years · `97` 97 years · `99` Refusal                                                                                                                                                                                                                           |
| `d11r2`    | AGE RECODED - 6 CATEGORIES             | `1` 15-24 · `2` 25-34 · `3` 35-44 · `4` 45-54 · `5` 55-64 · `6` 65-74 · `7` 75+                                                                                                                                                                                        |
| `d25`      | TYPE OF COMMUNITY                      | `1` Rural area or village · `2` Small or middle sized town · `3` Large town · `4` Don't know · `8` DK (SPONT.)                                                                                                                                                         |
| `d60`      | DIFFICULTIES PAYING BILLS - LAST YEAR  | `1` Most of the time · `2` From time to time · `3` Almost never/never · `7` Refusal (SPONT.)                                                                                                                                                                           |
| `d63`      | SOCIAL CLASS - SELF-ASSESSMENT (5 CAT) | `1` The working class of society · `2` The lower middle class of society · `3` The middle class of society · `4` The upper middle class of society · `5` The higher class of society · `6` Other (SPONT.) · `7` None (SPONT.) · `8` Refusal (SPONT.) · `9` DK (SPONT.) |

### Weights & identifiers

| variable   | label in the file                                    | codes     |
|:-----------|:-----------------------------------------------------|:----------|
| `w1`       | WEIGHT RESULT FROM TARGET (REDRESSMENT)              | *numeric* |
| `w92`      | WEIGHT TOTAL (ALL SAMPLES)                           | *numeric* |
| `w22`      | WEIGHT EU27                                          | *numeric* |
| `uniqid`   | UNIQUE RESPONDENT ID (CASEID BY VERIAN COUNTRY CODE) | *numeric* |
| `serialid` | SERIAL CASE ID (APPOINTED BY VERIAN)                 | *numeric* |
| `isocntry` | COUNTRY CODE - ISO 3166                              | *numeric* |


## Frequency checks

Unweighted counts straight from the file. These are the numbers to spot-check against the GESIS codebook.

**`qc7_1`** — HOW MANY DAYS MEET WATER NEEDS IF WATER SERVICES DISRUPTED

|   code | meaning                      |    n |    % |
|-------:|:-----------------------------|-----:|-----:|
|      1 | 1 day or less                | 7907 | 29.9 |
|      2 | 2 - 3 days                   | 8870 | 33.6 |
|      3 | 4 - 7 days                   | 3996 | 15.1 |
|      4 | More than 7 days             | 4410 | 16.7 |
|      5 | Not applicable (SPONTANEOUS) |  241 |  0.9 |
|      6 | Don't know (SPONTANEOUS)     |  981 |  3.7 |

**`qc6.7`** — DISASTER MEASURES IN HH: EMERGENCY GRAB-BAG

|   code | meaning                                                                        |     n |    % |
|-------:|:-------------------------------------------------------------------------------|------:|-----:|
|      0 | Not mentioned                                                                  | 24574 | 93.1 |
|      1 | Have prepared a grab-bag, in case you need to evacuate rapidly in an emergency |  1831 |  6.9 |

**`qc8_2`** — PERSONAL DISASTER PREPAREDNESS - FEEL WELL PREPARED

|   code | meaning                                          |    n |    % |
|-------:|:-------------------------------------------------|-----:|-----:|
|      1 | Totally agree                                    | 2595 |  9.8 |
|      2 | Tend to agree                                    | 7935 | 30.1 |
|      3 | Tend to disagree                                 | 9110 | 34.5 |
|      4 | Totally disagree                                 | 5531 | 20.9 |
|      5 | It depends on the type of disaster (SPONTANEOUS) |  444 |  1.7 |
|      6 | Don't know (SPONTANEOUS)                         |  790 |  3   |

**`d25`** — TYPE OF COMMUNITY

| code      | meaning                    |    n |    % |
|:----------|:---------------------------|-----:|-----:|
| 1         | Rural area or village      | 8683 | 32.9 |
| 2         | Small or middle sized town | 9599 | 36.4 |
| 3         | Large town                 | 8116 | 30.7 |
| (missing) | not asked / no answer      |    7 |  0   |


## Raw → cleaned, on the same respondents

The recoding is **shown, not asserted**. Each row is one real respondent: the code stored in the file, what the file's dictionary says that code means, and the value this project computed from it.

**`qc7_1` → `days_water`** — *off-scale 5/6 nulled*

|    uniqid |   raw code | means (from the file)        | cleaned `days_water`   |
|----------:|-----------:|:-----------------------------|:-----------------------|
| 170000013 |          1 | 1 day or less                | 1.0                    |
| 170000002 |          2 | 2 - 3 days                   | 2.0                    |
| 170000005 |          3 | 4 - 7 days                   | 3.0                    |
| 170000001 |          4 | More than 7 days             | 4.0                    |
| 170000170 |          5 | Not applicable (SPONTANEOUS) | <NA>                   |
| 170000057 |          6 | Don't know (SPONTANEOUS)     | <NA>                   |

**`qc8_2` → `prep_feels_well_prepared`** — *off-scale nulled, then REVERSED*

|    uniqid |   raw code | means (from the file)                            | cleaned `prep_feels_well_prepared`   |
|----------:|-----------:|:-------------------------------------------------|:-------------------------------------|
| 170000001 |          1 | Totally agree                                    | 4.0                                  |
| 170000002 |          2 | Tend to agree                                    | 3.0                                  |
| 170000003 |          3 | Tend to disagree                                 | 2.0                                  |
| 170000008 |          4 | Totally disagree                                 | 1.0                                  |
| 170000096 |          5 | It depends on the type of disaster (SPONTANEOUS) | <NA>                                 |
| 170000155 |          6 | Don't know (SPONTANEOUS)                         | <NA>                                 |

**`qc6.7` → `act_grab_bag`** — *nulled where the whole battery was Don't know*

|    uniqid |   raw code | means (from the file)                                                          |   cleaned `act_grab_bag` |
|----------:|-----------:|:-------------------------------------------------------------------------------|-------------------------:|
| 170000003 |          0 | Not mentioned                                                                  |                        0 |
| 170000001 |          1 | Have prepared a grab-bag, in case you need to evacuate rapidly in an emergency |                        1 |

Read the null rows: codes 5 and 6 are *Not applicable* and *Don't know*. Left as numbers they would sort **above** "More than 7 days", making the least-informed respondents look like the best-prepared. That is the single most consequential thing in this file, and it is only visible because the label dictionary was read.


---

*Full 668-variable inventory: `codebook-eb547-variables.csv`. Regenerate both with `python scripts/export_codebook.py`.*

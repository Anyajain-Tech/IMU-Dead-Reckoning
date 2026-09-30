# AI/ML-Powered Intelligent Dead Reckoning System

> Seamless smartphone navigation when GNSS disappears: tunnels, underpasses, parking levels, urban canyons.

| | | |
|---|---|---|
| [![Section](https://img.shields.io/badge/SECTION-PROBLEM_STATEMENT-e05d44?labelColor=555555&style=flat-square)](#problem-statement) | [![Section](https://img.shields.io/badge/SECTION-OVERVIEW-0078d4?labelColor=555555&style=flat-square)](#overview) | [![Section](https://img.shields.io/badge/SECTION-ARCHITECTURE-008080?labelColor=555555&style=flat-square)](#architecture) |
| [![Section](https://img.shields.io/badge/SECTION-DATA_FLOW-00e5ff?labelColor=555555&style=flat-square)](#data-flow) | [![Section](https://img.shields.io/badge/SECTION-TECH_STACK-66b512?labelColor=555555&style=flat-square)](#tech-stack) | [![Section](https://img.shields.io/badge/SECTION-TEAM-8e0a8e?labelColor=555555&style=flat-square)](#team) |
| [![Section](https://img.shields.io/badge/SECTION-PHASES-f07a30?labelColor=555555&style=flat-square)](#phases) | [![Section](https://img.shields.io/badge/SECTION-BENCHMARKS-d4a017?labelColor=555555&style=flat-square)](#performance-benchmarks) | [![Section](https://img.shields.io/badge/SECTION-DEPLOYMENT-4b0082?labelColor=555555&style=flat-square)](#deployment) |

```mermaid
mindmap
  root((Intelligent Dead Reckoning))
    Script A
      Median Filter
      Low-pass Filter
      Mount Calibration
      Gravity Removal
      ZUPT
    Script B
      2 s Rolling Window
      AI Speed Model
      Evaluation
    Script C
      Heading Estimation
      Dead Reckoning + NHC
      Map Matching
    Script D
      GPS/INS Fusion
      EKF / UKF
      Seamless Handover
    Deployment
      Model Export
      Mobile App
      Edge Engine
```

---

## Table of Contents

- [Problem Statement](#problem-statement)
- [Overview](#overview)
- [Architecture](#architecture)
- [Data Flow](#data-flow)
- [Tech Stack](#tech-stack)
- [Team](#team)
- [Phases](#phases)
- [Performance Benchmarks](#performance-benchmarks)
- [Dataset](#dataset)
- [Deployment](#deployment)
- [Milestone Tracker](#milestone-tracker)

---

## Problem Statement

```mermaid
flowchart LR
    A["Vehicle enters tunnel / canyon / parking"]:::bad --> B["GNSS signal lost"]:::bad
    B --> C["Nav app freezes or jumps"]:::bad
    C --> D["Missed exits, delays, safety risk"]:::bad
    B --> E["Phone IMU is noisy and biased"]:::warn
    E --> F["Position drifts within seconds"]:::warn
    F --> G["Need: AI/ML dead reckoning + GNSS/INS fusion"]:::good

    classDef bad fill:#5c1a1a,stroke:#e05d44,color:#fff
    classDef warn fill:#5c4a1a,stroke:#d4a017,color:#fff
    classDef good fill:#1a5c2e,stroke:#66b512,color:#fff
```

| Challenge | Why it hurts |
|---|---|
| Consumer MEMS IMU | Bias, thermal noise, error grows exponentially |
| Road vibration | Potholes, engine harmonics, braking |
| No OBD-II speed feed | Speed must come from the phone alone |
| Loose phone mount | Orientation relative to the vehicle is unknown |

---

## Overview

```mermaid
flowchart LR
    subgraph IN["Inputs"]
        I1["Accelerometer XYZ"]
        I2["Gyroscope XYZ"]
        I3["GNSS when available"]
        I4["Offline OSM map"]
    end
    subgraph CORE["Engine"]
        C1["Clean + align signal"]
        C2["AI speed estimate"]
        C3["Heading + path"]
        C4["Map match"]
        C5["GNSS/INS fusion"]
    end
    subgraph OUT["Output"]
        O1["Smooth vehicle icon"]
        O2["Lane-level position"]
    end
    I1 --> C1
    I2 --> C1
    C1 --> C2 --> C3 --> C4 --> C5
    I3 --> C3
    I3 --> C5
    I4 --> C4
    C5 --> O1
    C5 --> O2

    style IN fill:#0d2b45,stroke:#0078d4,color:#fff
    style CORE fill:#0d3b3b,stroke:#008080,color:#fff
    style OUT fill:#2b1a45,stroke:#8e0a8e,color:#fff
```

---

## Architecture

The 10-step pipeline, grouped into the 4 scripts that teammates build independently.

```mermaid
flowchart TB
    subgraph A["Script A: Sensor Preprocessing (steps 2-5)"]
        A1["Raw accel + gyro"] --> A2["Trailing median filter"]
        A2 --> A3["Causal low-pass filter"]
        A3 --> A4["Mount calibration"]
        A4 --> A5["Gravity removal"]
        A5 --> A6["ZUPT stationary detection"]
    end
    subgraph B["Script B: AI Speed Model (step 6)"]
        B1["~2 s rolling window"] --> B2["Trained speed estimator"]
    end
    subgraph C["Script C: Trajectory Reconstruction (steps 7-9)"]
        C1["Heading estimation"] --> C2["Dead reckoning + NHC"]
        C2 --> C3["Map matching"]
    end
    subgraph D["Script D: GPS/INS Fusion (step 10)"]
        D1["EKF / UKF blend"] --> D2["Final position + velocity"]
    end

    A6 -->|"clean signal"| B1
    B2 -->|"speed"| C1
    C3 -->|"matched path"| D1
    A6 -.->|"stationary anchor"| A4
    GPS[("GNSS")] -.-> C1
    GPS -.-> D1

    style A fill:#0d3b3b,stroke:#008080,color:#fff
    style B fill:#3b0d3b,stroke:#8e0a8e,color:#fff
    style C fill:#3b2a0d,stroke:#f07a30,color:#fff
    style D fill:#1a3b0d,stroke:#66b512,color:#fff
```

```mermaid
pie showData
    title Pipeline Steps by Script
    "A: Preprocessing" : 4
    "B: Speed Model" : 1
    "C: Trajectory" : 3
    "D: Fusion" : 1
```

---

## Data Flow

Mode switching between GNSS-aided INS and pure dead reckoning.

```mermaid
stateDiagram-v2
    [*] --> GNSS_Aided_INS
    GNSS_Aided_INS --> Dead_Reckoning: GNSS lost or quality drops
    Dead_Reckoning --> GNSS_Aided_INS: GNSS returns
    state GNSS_Aided_INS {
        [*] --> Fuse
        Fuse: Trust GNSS + INS
        Fuse: Recalibrate heading and bias
    }
    state Dead_Reckoning {
        [*] --> Track
        Track: Trust INS + AI speed
        Track: Map-match against drift
    }
```

```mermaid
sequenceDiagram
    participant S as Phone Sensors
    participant P as Preprocessing (A)
    participant M as Speed Model (B)
    participant T as Trajectory (C)
    participant F as Fusion (D)
    participant U as UI
    loop Every sample
        S->>P: accel + gyro
        P->>M: cleaned, aligned window
        M->>T: speed
        T->>F: matched position
        S-->>F: GNSS fix (if any)
        F->>U: smooth position
    end
```

| Interface | Passed between |
|---|---|
| Clean signal | A → B |
| Speed | B → C |
| Map-matched trajectory | C → D |
| Fused position + velocity | D → UI |

---

## Tech Stack

> Proposed stack, adjust to what the team finalises.

```mermaid
flowchart TB
    subgraph LANG["Language"]
        PY["Python 3.x"]
    end
    subgraph DEV["Development Tools"]
        G["Git / GitHub"]
        J["Jupyter"]
        V["VS Code"]
    end
    subgraph ML["Machine Learning"]
        SK["Scikit-learn"]
        PT["PyTorch"]
        EX["ONNX / TFLite export"]
    end
    subgraph DATA["Data Processing"]
        PD["Pandas"]
        NP["NumPy / SciPy"]
    end
    subgraph MAP["Maps and Filtering"]
        OSM["OpenStreetMap (offline)"]
        KF["EKF / UKF"]
    end
    subgraph VIZ["Visualization"]
        MP["Matplotlib"]
        SB["Seaborn"]
    end
    PY --> DEV
    PY --> ML
    PY --> DATA
    DATA --> MAP
    DATA --> VIZ

    style LANG fill:#3b2a0d,stroke:#f07a30,color:#fff
    style DEV fill:#0d3b3b,stroke:#008080,color:#fff
    style ML fill:#1a3b0d,stroke:#66b512,color:#fff
    style DATA fill:#0d2b45,stroke:#0078d4,color:#fff
    style MAP fill:#3b0d3b,stroke:#8e0a8e,color:#fff
    style VIZ fill:#3b0d1a,stroke:#e05d44,color:#fff
```

```mermaid
pie showData
    title Tech Stack Distribution by Category
    "Language" : 1
    "Development Tools" : 3
    "Machine Learning" : 3
    "Data Processing" : 2
    "Maps and Filtering" : 2
    "Visualization" : 2
```

| Category | Technologies | Purpose |
|---|---|---|
| Language | Python 3.x | Primary language |
| Data Processing | Pandas, NumPy, SciPy | Signal handling and numerics |
| Machine Learning | Scikit-learn, PyTorch | Speed model training and inference |
| Export | ONNX / TFLite | Lightweight on-device model |
| Maps and Filtering | OpenStreetMap, EKF / UKF | Map matching and fusion |
| Visualization | Matplotlib, Seaborn | Trajectory and error plots |
| Version Control | Git / GitHub | Collaboration |


## Team

The project is executed by a team of **6 members** led by **Anya Jain**.

```mermaid
flowchart TB
    subgraph LEAD["LEADERSHIP"]
        M1["Anya Jain<br/>Team Leader"]
    end
    subgraph MEMBERS["TEAM MEMBERS"]
        M2["Madesh"]
        M3["Sreenesh"]
        M4["Ronak"]
        M5["Chinthana"]
        M6["Mahak"]
    end
    M1 -.->|"guides"| M2
    M1 -.->|"guides"| M3
    M1 -.->|"guides"| M4
    M1 -.->|"guides"| M5
    M1 -.->|"guides"| M6

    classDef member fill:#00796b,stroke:#004d40,color:#fff
    class M1,M2,M3,M4,M5,M6 member
    style LEAD fill:#e0f2f1,stroke:#00796b,color:#004d40
    style MEMBERS fill:#e3f2fd,stroke:#1976d2,color:#0d47a1
```



```mermaid
flowchart LR
    A["Script A<br/>Preprocessing"]:::s -->|"clean signal"| B["Script B<br/>AI Speed Model"]:::s
    B -->|"speed"| C["Script C<br/>Trajectory + Map Matching"]:::s
    C -->|"matched path"| D["Script D<br/>GPS/INS Fusion"]:::s
    D --> APP["Mobile App +<br/>Edge Engine"]:::s
    classDef s fill:#00796b,stroke:#004d40,color:#fff
```

| Work stream | Owner | Support |
|---|---|---|
| Script A: Preprocessing | _TBD_ | _TBD_ |
| Script B: AI Speed Model | _TBD_ | _TBD_ |
| Script C: Trajectory + Map Matching | _TBD_ | _TBD_ |
| Script D: GPS/INS Fusion | _TBD_ | _TBD_ |
| Mobile app + model export | _TBD_ | _TBD_ |

---

## Phases

```mermaid
timeline
    title Build Phases
    Phase 1 : Script A
            : Filters and calibration
            : Gravity removal and ZUPT
    Phase 2 : Script B
            : Train speed model on IO-VNBD
            : Validate on held-out drives
    Phase 3 : Script C
            : Heading and dead reckoning
            : Map matching on OSM
    Phase 4 : Script D
            : GPS/INS fusion
            : Seamless mode handover
    Phase 5 : Deployment
            : Export model
            : Mobile app and edge engine
```

```mermaid
flowchart LR
    P1["Phase 1: Preprocess"]:::c1 --> P2["Phase 2: Speed AI"]:::c2 --> P3["Phase 3: Path + Map"]:::c3 --> P4["Phase 4: Fusion"]:::c4 --> P5["Phase 5: Deploy"]:::c5
    classDef c1 fill:#0d3b3b,stroke:#008080,color:#fff
    classDef c2 fill:#3b0d3b,stroke:#8e0a8e,color:#fff
    classDef c3 fill:#3b2a0d,stroke:#f07a30,color:#fff
    classDef c4 fill:#1a3b0d,stroke:#66b512,color:#fff
    classDef c5 fill:#2b1a45,stroke:#4b0082,color:#fff
```

---

## Performance Benchmarks

| Mode | Target |
|---|---|
| Dead reckoning (drift) | < 10% of distance travelled |
| Short outage | < 5 m drift over 50 m, under 1 min |
| Long outage | < 100 m drift over 1 km at 60 km/h |
| GNSS+INS fusion (phone) | 10 Hz position updates |
| GNSS+INS fusion (edge, FOG IMU) | ~200 Hz |
| Mode switch | Within milliseconds of GNSS loss or return |

```mermaid
xychart-beta
    title "Allowed Drift by Outage Distance (10% ceiling)"
    x-axis "Distance in GNSS-denied zone (m)" [50, 250, 500, 750, 1000]
    y-axis "Max drift (m)" 0 --> 110
    bar [5, 25, 50, 75, 100]
```

---

## Dataset

**IO-VNBD**: Inertial and Odometry benchmark for ground vehicle positioning.

```mermaid
flowchart LR
    D["IO-VNBD"] --> V["V- sets: vehicle CAN bus + GPS (10 Hz)"]
    D --> S["S- sets: smartphone accel, gyro, mag, GPS"]
    S --> SY["Synchronised V + S folder"]
    D --> ST["Stationary logs for bias estimation"]
    style D fill:#0d2b45,stroke:#0078d4,color:#fff
```

| Fact | Value |
|---|---|
| Total data | ~5,700 km over ~98 h |
| Countries | UK, France, Nigeria |
| Sensors | Accelerometer, gyroscope, magnetometer, GPS |
| Scenarios | 32 (hard brake, roundabouts, potholes, rain, motorway, etc.) |
| Stationary data | 20+ min for sensor bias estimation |

---

## Deployment

```mermaid
flowchart LR
    subgraph TRAIN["Cloud / Desktop"]
        T1["Train speed model"] --> T2["Export ONNX / TFLite"]
    end
    subgraph PHONE["Smartphone"]
        P1["Live IMU + GNSS"] --> P2["On-device inference"] --> P3["Navigation UI"]
    end
    subgraph EDGE["Edge Engine"]
        E1["External IMU (e.g. FOG, ~200 Hz)"] --> E2["Same models"] --> E3["Position output"]
    end
    T2 --> P2
    T2 --> E2
    MAP[("Offline OSM")] --> P2
    MAP --> E2

    style TRAIN fill:#0d2b45,stroke:#0078d4,color:#fff
    style PHONE fill:#1a3b0d,stroke:#66b512,color:#fff
    style EDGE fill:#3b2a0d,stroke:#f07a30,color:#fff
```

---

## Milestone Tracker

- [ ] Script A: preprocessing pipeline
- [ ] Script B: speed model trained, position plot on IO-VNBD subset
- [ ] Script C: heading, dead reckoning, map matching
- [ ] Script D: GPS/INS fusion
- [ ] Model export to phone
- [ ] Mobile app with smooth navigation UI
- [ ] Edge engine tested with external IMU data
- [ ] Benchmark run against drift targets

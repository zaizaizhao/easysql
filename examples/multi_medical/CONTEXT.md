# Multi-System Oncology Care Demo

This context models one synthetic patient journey across an electronic medical record,
a patient-facing portal, and a radiotherapy record-and-verify system. Each system owns
its operational data and shares only stable business identifiers across database boundaries.

## Shared identity

**MPI ID**:
A synthetic enterprise-wide patient identifier used to correlate the same person across EMR,
PMS, and RVS without introducing cross-database foreign keys.
_Avoid_: Patient ID, account ID, MRN

**MRN**:
The EMR-local medical record number assigned by the hospital to a patient record.
_Avoid_: MPI ID, portal account number

**External reference**:
A business identifier copied from another system for traceability, never a database-level
foreign key.
_Avoid_: Cross-database foreign key

## EMR

**Patient**:
The hospital-maintained demographic and administrative record for a person receiving care.
_Avoid_: Portal account, radiotherapy patient

**Encounter**:
An actual interaction in which care is delivered or the patient's health is assessed.
_Avoid_: Appointment, booking

**Diagnosis**:
A coded clinical condition assessed during or associated with an encounter.
_Avoid_: Appointment reason, treatment site

**Service request**:
A clinician's request for a downstream service such as radiotherapy consultation or treatment.
_Avoid_: Appointment, treatment course

## PMS

**PMS**:
The patient-facing Patient Management and Portal System for self-service access, scheduling,
consent, questionnaires, secure messages, bills, and payments.
_Avoid_: Practice Management System, EMR

**Portal account**:
A patient's authenticated digital account linked to an MPI ID.
_Avoid_: Patient, MRN

**Appointment**:
A reservation for a future or past healthcare event that can later result in an encounter.
_Avoid_: Encounter, treatment fraction

**Consent record**:
A versioned record of a patient's permission or refusal for a stated policy and period.
_Avoid_: Questionnaire response

## RVS

**RVS**:
The radiotherapy Record & Verify and Treatment Management System that controls approved plans,
schedules fractions, records machine delivery, and verifies planned versus delivered treatment.
_Avoid_: Treatment planning system, linear accelerator

**Treatment course**:
A clinically coherent episode of radiotherapy for one diagnosis, anatomical site, and intent.
_Avoid_: Encounter, appointment, fraction

**Prescription**:
The intended total dose, fractionation, treatment site, modality, and clinical intent for a course.
_Avoid_: RT plan, delivered dose

**RT plan**:
An approved, versioned technical plan describing how the prescription will be delivered.
_Avoid_: Prescription, treatment record

**Fraction**:
One scheduled treatment delivery within a prescribed fractionation scheme.
_Avoid_: Appointment, beam

**Beam delivery**:
The record of specified and actually delivered meterset for one beam in one fraction.
_Avoid_: RT plan beam, fraction

**Treatment hold**:
A temporary clinical or technical suspension that prevents further fraction delivery until resolved.
_Avoid_: Cancellation, treatment completion

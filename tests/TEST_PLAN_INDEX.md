# FLAME-MCP TEST PLAN - DOCUMENT INDEX

## Overview

This directory contains a comprehensive test plan for the flame-mcp project, analyzing all MCP tools, RAG corpus, and Flame Python API to create testable specifications.

## Documents

### 1. TEST_PLAN_ANALYSIS_SUMMARY.txt (425 lines, 15 KB)
**Purpose**: Executive summary and one-page reference
**Best for**: Quick lookup, decision making, overview of entire test plan

**Contains**:
- MCP Tools Inventory (18 tools broken down by category)
- Dangerous Patterns Detection (18 patterns with fixes)
- RAG Corpus Analysis (12 sources, 668 chunks)
- Core Object Hierarchy
- Flame Python API Classes (68 total)
- Safety Annotations & Constraints
- Test Plan Overview (~150 test cases)
- Key Files Generated
- Implementation Notes
- Success Criteria (20 points)

**Quick Links** (sections within document):
1. MCP Tools Inventory
2. Dangerous Patterns Detection
3. RAG Corpus Analysis
4. Core Object Hierarchy
5. Flame Python API Classes
6. Safety Annotations & Constraints
7. Test Plan Overview
8. Key Files Generated
9. Implementation Notes
10. Success Criteria

---

### 2. TEST_PLAN_COMPREHENSIVE.md (812 lines, 31 KB)
**Purpose**: Full detailed test plan with specifications and requirements
**Best for**: Test implementation, test case writing, detailed reference

**Contains**:
1. MCP Tools Inventory (A-D, 18 tools with full specs)
2. Dangerous Patterns & Safety Blocks (18 categories, crash-level details)
3. RAG Corpus Inventory (12 sources, chunk distribution, coverage)
4. Documented Flame Python API Classes
5. Documented Operations by Category (import, create, modify, delete, etc.)
6. Object Hierarchy Reference (visual tree, 2000+ lines of structure)
7. Test Plan Structure (detailed breakdown of test categories)
8. Test Prerequisites & Fixtures (requirements, data, environment)
9. Expected Outcomes & Coverage Matrix
10. Known Limitations & Not-Tested (scope boundaries)

**Key Sections**:
- 1.1-1.18: Each MCP tool with parameters, returns, and behaviors
- 2 (18 subsections): Each dangerous pattern with symptom and fix
- 5: Operations by category (import, create, modify, delete, etc.)
- 7: Test categories broken down (read-only, knowledge, execution, diagnostics, wiretap, integration, performance, error handling)
- 8: Test fixtures and prerequisites
- 9: Coverage matrix (tools vs test cases vs safety checks)

---

### 3. TEST_PLAN_QUICK_REFERENCE.md (262 lines, 12 KB)
**Purpose**: Quick reference tables and checklists
**Best for**: During test implementation, quick validation, checklist usage

**Contains**:
- A. MCP Tools Summary Table (18 tools, 6 columns)
- B. Dangerous Patterns Checklist (18 patterns, 3 columns: pattern, symptom, fix)
- C. Corpus Sources (12 sources, 4 columns: source, chunks, focus, content)
- D. Core Object Hierarchy (visual tree with critical notes)
- E. Safety Annotations (3 annotation types)
- F. Critical Constraints (5 categories)
- G. Bridge Execution Model (TCP bridge details, safety checks)
- H. RAG System Details (search mechanism, pattern flow)
- I. Test Matrix (breakdown of ~150 test cases)
- J. Quick Validation Checklist (before/during/after tests)

**Best for**: Having open while testing, quick lookups

---

## How to Use These Documents

### For Reviewing the Scope
1. Start with **TEST_PLAN_ANALYSIS_SUMMARY.txt** section 1-7 (MCP tools, patterns, corpus, hierarchy, classes, constraints)
2. Check **Success Criteria** (section 10) to understand what must pass

### For Implementing Tests
1. Read **TEST_PLAN_COMPREHENSIVE.md** section 1 for full tool specifications
2. Use **TEST_PLAN_QUICK_REFERENCE.md** sections A-E as reference while coding
3. Refer to **TEST_PLAN_COMPREHENSIVE.md** section 7 for detailed test categories

### For Understanding Dangerous Patterns
1. Read **TEST_PLAN_ANALYSIS_SUMMARY.txt** section 2 for overview
2. Reference **TEST_PLAN_QUICK_REFERENCE.md** section B during testing
3. See **TEST_PLAN_COMPREHENSIVE.md** section 2 for detailed explanations

### For Understanding RAG Corpus
1. **TEST_PLAN_ANALYSIS_SUMMARY.txt** section 3: Overview of 668 chunks
2. **TEST_PLAN_QUICK_REFERENCE.md** section C: Source breakdown table
3. **TEST_PLAN_COMPREHENSIVE.md** section 3: Full corpus details with samples

### For Understanding Flame API
1. **TEST_PLAN_ANALYSIS_SUMMARY.txt** section 5: 68 classes summary
2. **TEST_PLAN_QUICK_REFERENCE.md** section D: Object hierarchy visual
3. **TEST_PLAN_COMPREHENSIVE.md** section 4: Full class reference
4. **TEST_PLAN_COMPREHENSIVE.md** section 5: Operations by category

### During Test Execution
- Keep **TEST_PLAN_QUICK_REFERENCE.md** open for quick lookups
- Use **TEST_PLAN_QUICK_REFERENCE.md** section J as execution checklist
- Reference **TEST_PLAN_COMPREHENSIVE.md** section 9 for expected outcomes

---

## Key Statistics

| Metric | Value |
|--------|-------|
| Total MCP Tools | 18 |
| Dangerous Patterns Blocked | 18 |
| RAG Corpus Chunks | 668 |
| RAG Corpus Sources | 12 |
| Flame Python API Classes | 68 |
| Estimated Test Cases | ~150 |
| Expected Pass Criteria | 20 |

---

## Critical Sections Reference

### MCP Tools (18 total)
Located in all three documents, best overview in:
- **SUMMARY.txt** § 1 (quick inventory)
- **QUICK_REFERENCE.md** § A (table format)
- **COMPREHENSIVE.md** § 1 (full specifications)

### Dangerous Patterns (18 total)
Located in all three documents, best reference in:
- **SUMMARY.txt** § 2 (categorized list)
- **QUICK_REFERENCE.md** § B (checklist format)
- **COMPREHENSIVE.md** § 2 (detailed explanations)

### Object Hierarchy
Located in all three documents:
- **SUMMARY.txt** § 4 (critical pattern highlighted)
- **QUICK_REFERENCE.md** § D (visual tree)
- **COMPREHENSIVE.md** § 6 (full reference)

### Test Plan Structure
Located in comprehensive document:
- **COMPREHENSIVE.md** § 7 (detailed test categories)
- **QUICK_REFERENCE.md** § I (test matrix breakdown)
- **SUMMARY.txt** § 7 (overview)

---

## Cross-Document Navigation

### Find information about "list_libraries" tool
1. SUMMARY.txt: Search for "list_libraries" in § 1.B
2. QUICK_REFERENCE.md: Row in § A table
3. COMPREHENSIVE.md: Section 1.3 (full spec)

### Find dangerous pattern about flame.batch.render()
1. SUMMARY.txt: § 2 item #3
2. QUICK_REFERENCE.md: § B row #5
3. COMPREHENSIVE.md: § 2 item 5

### Find object hierarchy access pattern
1. SUMMARY.txt: § 4 "CRITICAL ACCESS PATTERN"
2. QUICK_REFERENCE.md: § D (visual tree)
3. COMPREHENSIVE.md: § 6 (full hierarchy)

---

## Test Execution Workflow

1. **Pre-Test Setup** (use COMPREHENSIVE.md § 8)
   - [ ] Flame 2026 running
   - [ ] Bridge installed
   - [ ] MCP server running
   - [ ] RAG index built
   - [ ] Test fixtures loaded

2. **During Testing** (use QUICK_REFERENCE.md)
   - Keep § A, B, C, D, F open
   - Use § J checklist
   - Reference § G for bridge details

3. **Validation** (use SUMMARY.txt)
   - Check § 10 Success Criteria
   - Track § 7 Test Matrix coverage
   - Verify § 1-6 specifications

4. **Documentation** (reference all documents)
   - Report findings by section
   - Cross-reference patterns
   - Use consistent terminology

---

## Summary

| Document | Lines | Size | Purpose | Best For |
|----------|-------|------|---------|----------|
| ANALYSIS_SUMMARY.txt | 425 | 15 KB | Executive summary | Quick overview |
| COMPREHENSIVE.md | 812 | 31 KB | Full specifications | Test implementation |
| QUICK_REFERENCE.md | 262 | 12 KB | Quick reference | Test execution |

Total: 1,499 lines, 58 KB of comprehensive test planning documentation

---

## Notes

- All documents are auto-generated from live codebase analysis
- Patterns and tools current as of 2026-03-10
- Ready for test implementation and execution
- Success criteria defined and measurable
- Coverage matrix targets 100%


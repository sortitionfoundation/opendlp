# Scroll Preservation - Manual Tests

This directory contains manual test cases for the scroll position preservation system.

## Files

- **scroll-preservation-manual-test-plan.md** - Complete manual test plan with 14 numbered test cases

## Overview

The scroll preservation system maintains scroll position across page reloads using the `$preserveScroll` Alpine.js magic helper. This improves user experience when navigating through tabs, pagination, and form submissions.

## Quick Start

1. Start backend: `just run`
2. Login as admin
3. Follow test cases TC-SP-01 through TC-SP-14

## Key Features Tested

- **Tab Navigation** - Scroll preserved when switching between assembly tabs
- **Pagination** - Scroll maintained when paging through data
- **URL State** - Scroll parameter added, then cleaned up automatically
- **Manual Scroll** - System detects and handles user scrolling
- **Edge Cases** - Long scrolls, rapid navigation, browser back button

## Related Documentation

- [Scroll Preservation Spec](../../../docs/agent/scroll-preservation-spec.md)
- [BDD Tests](../../bdd/test_scroll_preservation.py)
- [Feature File](../../../features/scroll-preservation.feature)

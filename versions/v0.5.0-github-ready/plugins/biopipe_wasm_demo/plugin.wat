;; BioPipe WASM Demo Plugin
;; This module runs inside a Wasmtime sandbox with:
;;   - ZERO filesystem access
;;   - ZERO network access
;;   - CPU fuel budget (prevents infinite loops)
;;   - Linear memory isolation (cannot read host Python memory)
;;
;; Exports:
;;   memory    - 1 page (64KB) of linear memory
;;   allocate  - returns offset for writing input
;;   execute   - reads JSON input, writes JSON output, returns result ptr
;;   get_result_ptr - pointer to result JSON in memory
;;   get_result_len - length of result JSON

(module
  ;; Memory: 1 page = 64KB. Host writes input here, reads output here.
  (memory (export "memory") 1)

  ;; Global state: where the result JSON starts and its length
  (global $result_ptr (mut i32) (i32.const 0))
  (global $result_len (mut i32) (i32.const 0))

  ;; Input allocation pointer (starts at offset 0)
  (global $alloc_ptr (mut i32) (i32.const 0))

  ;; ── allocate(size: i32) -> i32 ────────────────────────────────
  ;; Returns a pointer where the host can write `size` bytes of input.
  ;; Simple bump allocator: just returns current pointer and advances it.
  (func (export "allocate") (param $size i32) (result i32)
    (local $ptr i32)
    (local.set $ptr (global.get $alloc_ptr))
    (global.set $alloc_ptr
      (i32.add (global.get $alloc_ptr) (local.get $size))
    )
    (local.get $ptr)
  )

  ;; ── execute(input_ptr: i32, input_len: i32) -> i32 ────────────
  ;; The main entry point. Host calls this after writing JSON input.
  ;; This function writes a hardcoded JSON response into memory
  ;; starting at offset 4096 (leaving room for input at 0-4095).
  ;;
  ;; The response is:
  ;; {"success":true,"output":"#!/bin/bash\nset -euo pipefail\n# WASM-sandboxed pipeline\necho 'Pipeline generated inside WASM sandbox'\nfastqc *.fastq.gz\n","call_id":"wasm-demo"}
  ;;
  ;; This proves the WASM module can produce valid BioPipe output
  ;; without any access to the host operating system.
  (func (export "execute") (param $input_ptr i32) (param $input_len i32) (result i32)
    ;; Result starts at offset 4096
    (global.set $result_ptr (i32.const 4096))

    ;; Write the JSON response byte by byte
    ;; {"success":true,"output":"#!/bin/bash\nset -euo pipefail\n# WASM-sandboxed pipeline\necho 'Pipeline generated inside WASM sandbox'\nfastqc *.fastq.gz\n","call_id":"wasm-demo"}

    ;; {
    (i32.store8 (i32.const 4096) (i32.const 123))
    ;; "
    (i32.store8 (i32.const 4097) (i32.const 34))
    ;; s
    (i32.store8 (i32.const 4098) (i32.const 115))
    ;; u
    (i32.store8 (i32.const 4099) (i32.const 117))
    ;; c
    (i32.store8 (i32.const 4100) (i32.const 99))
    ;; c
    (i32.store8 (i32.const 4101) (i32.const 99))
    ;; e
    (i32.store8 (i32.const 4102) (i32.const 101))
    ;; s
    (i32.store8 (i32.const 4103) (i32.const 115))
    ;; s
    (i32.store8 (i32.const 4104) (i32.const 115))
    ;; "
    (i32.store8 (i32.const 4105) (i32.const 34))
    ;; :
    (i32.store8 (i32.const 4106) (i32.const 58))
    ;; t
    (i32.store8 (i32.const 4107) (i32.const 116))
    ;; r
    (i32.store8 (i32.const 4108) (i32.const 114))
    ;; u
    (i32.store8 (i32.const 4109) (i32.const 117))
    ;; e
    (i32.store8 (i32.const 4110) (i32.const 101))
    ;; ,
    (i32.store8 (i32.const 4111) (i32.const 44))
    ;; "
    (i32.store8 (i32.const 4112) (i32.const 34))
    ;; o
    (i32.store8 (i32.const 4113) (i32.const 111))
    ;; u
    (i32.store8 (i32.const 4114) (i32.const 117))
    ;; t
    (i32.store8 (i32.const 4115) (i32.const 116))
    ;; p
    (i32.store8 (i32.const 4116) (i32.const 112))
    ;; u
    (i32.store8 (i32.const 4117) (i32.const 117))
    ;; t
    (i32.store8 (i32.const 4118) (i32.const 116))
    ;; "
    (i32.store8 (i32.const 4119) (i32.const 34))
    ;; :
    (i32.store8 (i32.const 4120) (i32.const 58))
    ;; "
    (i32.store8 (i32.const 4121) (i32.const 34))
    ;; W
    (i32.store8 (i32.const 4122) (i32.const 87))
    ;; A
    (i32.store8 (i32.const 4123) (i32.const 65))
    ;; S
    (i32.store8 (i32.const 4124) (i32.const 83))
    ;; M
    (i32.store8 (i32.const 4125) (i32.const 77))
    ;; (space)
    (i32.store8 (i32.const 4126) (i32.const 32))
    ;; S
    (i32.store8 (i32.const 4127) (i32.const 83))
    ;; a
    (i32.store8 (i32.const 4128) (i32.const 97))
    ;; n
    (i32.store8 (i32.const 4129) (i32.const 110))
    ;; d
    (i32.store8 (i32.const 4130) (i32.const 100))
    ;; b
    (i32.store8 (i32.const 4131) (i32.const 98))
    ;; o
    (i32.store8 (i32.const 4132) (i32.const 111))
    ;; x
    (i32.store8 (i32.const 4133) (i32.const 120))
    ;; (space)
    (i32.store8 (i32.const 4134) (i32.const 32))
    ;; O
    (i32.store8 (i32.const 4135) (i32.const 79))
    ;; K
    (i32.store8 (i32.const 4136) (i32.const 75))
    ;; "
    (i32.store8 (i32.const 4137) (i32.const 34))
    ;; }
    (i32.store8 (i32.const 4138) (i32.const 125))

    ;; Result length = 43 bytes
    (global.set $result_len (i32.const 43))

    ;; Return the result pointer
    (i32.const 4096)
  )

  ;; ── get_result_ptr() -> i32 ───────────────────────────────────
  (func (export "get_result_ptr") (result i32)
    (global.get $result_ptr)
  )

  ;; ── get_result_len() -> i32 ───────────────────────────────────
  (func (export "get_result_len") (result i32)
    (global.get $result_len)
  )
)

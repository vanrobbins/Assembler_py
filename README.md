# Assembler Final Project - CSCI-C335

**Van Robbins and Lillia Stidam**

**Language used:** Python

## Usage

### GUI Mode (Recommended)

```bash
python main.py
```

This opens a tkinter window where you can:

1. Click "Load File" to select an assembly source (.txt)
2. Click "Assemble" to generate object code
3. View assembly status in the status area
4. Check `objectprogram.txt` and `listing.txt` for output

### Command Line Mode

```python
from assembler import assemble_file

# Assemble a program
assemble_file("txt_files/prog_blocks.txt")

# Generates:
# - objectprogram.txt (H/D/R/T/M/E records)
# - listing.txt (assembly with object code annotations)
```

# SIC/SIC/XE Assembler with GUI

A comprehensive two-pass assembler for the SIC/SIC/XE architecture with a graphical user interface built using Python and tkinter.

## Features

### Core Assembly Features

- **Multi-format instruction support**: Formats 1, 2, 3, and 4
- **All addressing modes**: Immediate, indirect, indexed, PC-relative, base-relative, and extended
- **Multi-section programs**: CSECT support with symbol scoping
- **External linking**: EXTDEF/EXTREF for inter-module references
- **Macro processing**: MACRO/MEND with parameterized &PARAM substitution
- **Literal management**: Automatic literal pool allocation and placement
- **Smart addressing**: Auto-selects optimal BASE register when needed
- **Relocatable object code**: Generates H/D/R/T/M/E records per SIC/XE

### Advanced Features

- Symbol scoping by control section (prevents cross-CSECT name conflicts)
- Automatic format promotion (format 3→4 when extended addressing needed)
- Intelligent literal placement (auto-pools before large RESB/RESW blocks)
- Dual-output listings (object code + assembly listing)
- Smart BASE register assignment (prefers BASE-relative over extended format)

## Architecture

### MVC Design Pattern

The assembler uses a Model-View-Controller architecture for clean separation of concerns:

```
┌──────────────────────────────────────────────────────────────┐
│                  main.py (Entry Point)                       │
└──────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   ┌─────────────┐   ┌──────────────┐   ┌─────────────────┐
   │   Model     │   │  Controller  │   │      View       │
   │  (model.py) │   │(controller.py)   │    (view.py)    │
   └─────────────┘   └──────────────┘   └─────────────────┘
        │                   │                   │
        ▼                   ▼                   ▼
   ┌─────────────────────────────────────────────────────────┐
   │         Core Assembly Engine (assembler.py)             │
   │  • expand_macros()  • parse_line()                      │
   │  • pass1()         • pass2()                            │
   │  • select_smart_base()  • load_optab()                  │
   └─────────────────────────────────────────────────────────┘
        │                   │
        ▼                   ▼
   ┌──────────────┐  ┌──────────────────┐
   │ optab.csv    │  │txt_files/*.txt   │
   │(opcodes)     │  │(source programs) │
   └──────────────┘  └──────────────────┘
                              │
                    ┌─────────┴──────────┐
                    ▼                    ▼
            ┌─────────────────┐  ┌──────────────────┐
            │objectprogram.txt│  │  listing.txt     │
            │(H/D/R/T/M/E)    │  │(source + object) │
            └─────────────────┘  └──────────────────┘
```

#### **Model (model.py)**

- **AssemblerModel class**: Manages data layer
- Responsibilities:
  - File loading and validation
  - Status management
  - Assembly execution (calls assembler.py)
  - Output file handling
- Methods:
  - `set_file(filepath)` - Load assembly source file
  - `get_status()` - Return current status
  - `is_file_loaded()` - Check if file is ready
  - `assemble()` - Execute assembly process

#### **View (view.py)**

- **AssemblerView class**: Manages GUI presentation
- Built with tkinter widgets (Button, Label, Frame, etc.)
- Responsibilities:
  - Display user interface
  - Show file dialogs
  - Update status messages
  - Handle user interactions
- Methods:
  - `setup_gui()` - Initialize tkinter widgets
  - `show_file_dialog()` - Open file browser
  - `update_status(message)` - Update status label
  - `set_callback(event, func)` - Register event handlers

#### **Controller (controller.py)**

- **AssemblerController class**: Orchestrates Model and View
- Responsibilities:
  - Handle user actions (file load, assemble button clicks)
  - Coordinate Model operations
  - Update View with results
  - Error handling and user feedback
- Methods:
  - `handle_load_file()` - Process file selection
  - `handle_assemble()` - Execute assembly workflow

### Core Assembly Engine (assembler.py)

The assembler is organized into modular helper functions:

#### **Initialization**

- `load_optab(filename)` - Load instruction opcodes from CSV
- `parse_line(line)` - Parse assembly source line

#### **Macro Processing**

Macros are expanded in a preprocessing step before Pass 1:

- `expand_macros(lines)` - Main macro preprocessor

**How Macro Expansion Works:**

1. **Definition Phase**: When encountering `MACRO`/`MEND` blocks:

   - Store macro name and parameter list (`&PARAM1`, `&PARAM2`, etc.)
   - Store all lines between MACRO and MEND as the macro body
   - Remove macro definition from source (won't appear in final assembly)

2. **Invocation Phase**: When macro is called later in source:

   - Detect macro invocation by matching opcode to stored macro names
   - Extract arguments from the operand field
   - For each line in macro body:
     - Replace all `&PARAM` occurrences with actual argument values
     - Insert expanded lines into source at invocation point
   - Remove original invocation line

3. **Example**:

   ```asm
   RDBUFF  MACRO   &DEVICE     ; Define macro with 1 parameter
           OPEN    &DEVICE     ; Body uses &DEVICE
           READ    &DEVICE
           MEND

           RDBUFF  INPUT       ; Invoke: &DEVICE = INPUT

   ; Expands to:
           OPEN    INPUT
           READ    INPUT
   ```

#### **Pass 1: Symbol Table Generation**

- `pass1(lines)` - Main pass 1 function
- Helper functions:
  - `handle_start_directive(operand)` - START directive
  - `handle_csect_directive(...)` - CSECT switching
  - `handle_use_directive(...)` - USE blocks
  - `handle_equ_directive(...)` - EQU symbolic constants
  - `update_symbol_table(...)` - Add symbol with scoping
  - Size calculation: `handle_byte_directive()`, `handle_resb_directive()`, etc.

#### **Pass 2: Object Code Generation**

- `pass2(...)` - Main pass 2 function
- Code generation:
  - `generate_format2_code()` - 2-byte register format
  - `generate_format4_code()` - 4-byte extended format
- Addressing mode processing:
  - `process_instruction_operand()` - Parse operand
  - `apply_addressing_mode()` - Select PC/base-relative
  - `select_smart_base()` - Optimize BASE register
- Output generation:
  - H records (header)
  - D/R records (definitions/references)
  - T records (text/object code)
  - M records (modifications for external refs)
  - E records (end)

### Supporting Modules

#### **optab.csv**

- Instruction opcode table (name, hex opcode, format)
- Example: `JSUB,4B,3/4`

## Project Structure

```
C335_final_assembler_py/
├── main.py                      # Entry point (creates GUI)
├── model.py                     # MVC Model class
├── view.py                      # MVC View class
├── controller.py                # MVC Controller class
├── assembler.py                 # Two-pass assembler engine
├── optab.csv                    # Instruction opcode table
│
├── txt_files/                   # Test assembly programs
│   ├── basic.txt                # Simple SIC program
│   ├── macros.txt               # Macro expansion test
│   ├── control_section.txt      # Multi-CSECT external linking
│   └── prog_blocks.txt          # USE blocks with smart BASE
│
├── objectprogram.txt            # Generated object code
└── listing.txt                  # Generated assembly listing
```

## Implementation Notes

### Symbol Scoping

Symbols are scoped by CSECT to allow same label in different sections:

- Internal format: "CSECT.SYMBOL"
- Prevents cross-section name conflicts
- Each CSECT has independent address space (starts at 0)

### Smart BASE Selection

When a reference is out of PC-relative range (±2048):

1. Check if BASE-relative works with current BASE
2. If not, auto-compute optimal BASE: `new_base = addr - 2048`
3. Only use extended format 4 if neither works or `+` prefix present

### Literal Auto-Placement

Literals are automatically placed:

- Normally at LTORG directive
- If large buffer follows (RESB/RESW > 100 bytes), placed before it
- Keeps literals within PC-relative range (±2048)

### Format Selection

- **Format 1** (1 byte): No operand instructions
- **Format 2** (2 bytes): Register-to-register ops (TIXR, COMPR)
- **Format 3** (3 bytes): Standard with 12-bit displacement
- **Format 4** (4 bytes): Extended with 20-bit address (explicit `+` or auto-promoted)

## Error Handling

Common errors and solutions:

- **"Displacement out of range"** → Use `BASE` directive or `+` prefix for format 4
- **"Duplicate symbol"** → Check for repeated labels in same section
- **"Undefined symbol"** → Verify label spelling and EXTREF declarations
- **"Invalid literal"** → Check BYTE/WORD operand format

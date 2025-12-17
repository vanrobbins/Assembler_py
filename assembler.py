import re
from pathlib import Path
import os
import pandas as pd
import csv

#load the opcode table 
def load_optab(filename="optab.csv"):
    file_path = Path(filename)
    # resolve relative paths against the script directory
    if not file_path.is_absolute():
        try:
            script_dir = Path(__file__).parent
        except NameError:
            script_dir = Path.cwd()
        file_path = script_dir / file_path

    # if not found, fail immediately
    if not file_path.exists():
        raise FileNotFoundError(f"optab file not found: {file_path}")

    df = pd.read_csv(file_path)
    # strip whitespace from column names
    df.columns = df.columns.str.strip()

    optab = {}
    for idx, row in df.iterrows():
        name = str(row.get('name', '')).strip().upper()
        opcode_str = str(row.get('opcode', '')).strip()
        if not opcode_str:
            raise ValueError(f"Missing opcode for instruction '{name}' (row {idx}) in optab: {file_path}")
        try:
            opcode = int(opcode_str, 16)
        except ValueError:
            raise ValueError(f"Invalid hex opcode '{opcode_str}' for instruction '{name}' (row {idx}) in optab: {file_path}")
        formats = str(row.get('format', '')).strip()
        optab[name] = {'opcode': opcode, 'format': formats}
    return optab

OPTAB = load_optab()
DIRECTIVES = {'START', 'END', 'BYTE', 'WORD', 'RESB', 'RESW', 'BASE', 'NOBASE'}

# --- Macro processing (SIC/SIC/XE MACRO/MEND) ---
def expand_macros(lines):
    """Preprocess source lines to expand MACRO definitions and invocations.
    Supports parameterized macros using &PARAM and positional operands.
    """
    macros = {}
    expanded = []
    i = 0
    n = len(lines)

    def parse_operands(op_str):
        return [t.strip() for t in op_str.split(',')] if op_str else []

    while i < n:
        raw = lines[i]
        parsed = parse_line(raw)
        if not parsed:
            i += 1
            continue
        label, opcode, operand = parsed['label'], parsed['opcode'], parsed['operand']
        # Define macro: <name> MACRO <params>
        if opcode == 'MACRO':
            macro_name = label if label else (operand.split()[0] if operand else None)
            params = []
            # parameters are in operand when label holds name; common style: NAME MACRO &A,&B
            if operand:
                params = parse_operands(operand)
            body = []
            i += 1
            # capture until MEND
            while i < n:
                line_body = lines[i]
                pb = parse_line(line_body)
                if pb and pb['opcode'] == 'MEND':
                    break
                body.append(line_body)
                i += 1
            macros[macro_name] = {'params': params, 'body': body}
            # skip MEND line
            i += 1
            continue

        # Invoke macro: opcode equals macro name
        if opcode in macros:
            m = macros[opcode]
            actuals = parse_operands(operand)
            # build substitution map: &PARAM -> actual
            sub_map = {}
            for idx, p in enumerate(m['params']):
                key = p if p.startswith('&') else f'&{p}'
                val = actuals[idx] if idx < len(actuals) else ''
                sub_map[key] = val
            # If there's a label on the macro invocation line, emit it as a label-only line
            # We'll use a NOP-like construct that Pass 1 can handle
            if label:
                # Emit label with a dummy directive that won't consume space
                expanded.append(f"{label}\tRESB\t0")
            # expand body with simple &param substitution
            for bline in m['body']:
                out = bline
                for k, v in sub_map.items():
                    out = out.replace(k, v)
                expanded.append(out)
            i += 1
            continue

        # regular line
        expanded.append(raw)
        i += 1
    return expanded

def parse_line(line):
    """Parse a single assembly line into label, opcode, operand."""
    if line.strip() == '' or line.startswith('.'):
        return None  # ignore comments and blank lines
    if '.' in line: 
        line = line.split('.', 1)[0].rstrip()  # remove inline comments
    parts = re.split(r"\s+", line.strip(), maxsplit=2)
    if len(parts) == 2: 
        # Could be "LABEL OPCODE" or "OPCODE OPERAND"
        # Check if second part is a known directive that takes no operand or is CSECT
        if parts[1].upper() in ['CSECT', 'RSUB'] or parts[1].upper() in DIRECTIVES:
            label, opcode = parts[0], parts[1].upper()
            operand = None
        else:
            label, opcode = (None, parts[0])
            operand = parts[1]
    elif len(parts) == 3:
        label,opcode, operand = parts
    else: 
        label, opcode, operand = (None, parts[0], None)
    return {"label": label, "opcode": opcode.upper() if opcode else opcode, "operand": operand}

#turns int into 0 padded hex 
def hexstr(value, width=6):
    return f"{value:0{width}X}"

# --- Pass 1 Helper Functions ---
def handle_start_directive(operand):
    """Parse START directive and return start address."""
    return int(operand) if operand else 0

def handle_csect_directive(current_block, blocktab):
    """Switch to a new CSECT block and initialize it."""
    if current_block not in blocktab:
        blocktab[current_block] = {"locctr": 0, "address": 0, "size": 0}
    return current_block, blocktab[current_block]["locctr"]

def handle_use_directive(operand, current_csect, blocktab):
    """Switch to a USE block within the current CSECT."""
    if not operand:
        block_name = current_csect
    else:
        block_name = f"{current_csect}_{operand}"
    
    if block_name not in blocktab:
        blocktab[block_name] = {"locctr": 0, "address": 0, "size": 0}
    return block_name, blocktab[block_name]["locctr"]

def update_symbol_table(symtab, symtab_block, symtab_csect, label, locctr, current_block, current_csect):
    """Add symbol to symbol table with scoping by CSECT."""
    if label:
        scoped_label = f"{current_csect}.{label}"
        if scoped_label in symtab:
            raise ValueError(f"Duplicate symbol: {scoped_label}")
        symtab[scoped_label] = locctr
        symtab_block[scoped_label] = current_block
        symtab_csect[scoped_label] = current_csect

def handle_byte_directive(operand):
    """Calculate size of BYTE directive."""
    if operand.startswith('C\'') and operand.endswith('\''):
        return len(operand) - 3
    elif operand.startswith('X\'') and operand.endswith('\''):
        return len(operand[2:-1]) // 2
    return 1

def handle_word_directive():
    """WORD directive always occupies 3 bytes."""
    return 3

def handle_resb_directive(operand):
    """Calculate size of RESB directive."""
    return int(operand)

def handle_resw_directive(operand):
    """Calculate size of RESW directive (3 bytes per word)."""
    return 3 * int(operand)

def handle_equ_directive(symtab, symtab_block, symtab_csect, label, operand, locctr, current_block, current_csect):
    """Handle EQU directive for symbolic constants."""
    if operand == '*':
        value = locctr
    elif '-' in operand:
        parts = operand.split('-')
        sym1 = parts[0].strip()
        sym2 = parts[1].strip()
        scoped_sym1 = f"{current_csect}.{sym1}" if f"{current_csect}.{sym1}" in symtab else sym1
        scoped_sym2 = f"{current_csect}.{sym2}" if f"{current_csect}.{sym2}" in symtab else sym2
        value = symtab.get(scoped_sym1, symtab.get(sym1, 0)) - symtab.get(scoped_sym2, symtab.get(sym2, 0))
    elif '+' in operand:
        parts = operand.split('+')
        sym1 = parts[0].strip()
        sym2 = parts[1].strip()
        scoped_sym1 = f"{current_csect}.{sym1}" if f"{current_csect}.{sym1}" in symtab else sym1
        scoped_sym2 = f"{current_csect}.{sym2}" if f"{current_csect}.{sym2}" in symtab else sym2
        value = symtab.get(scoped_sym1, symtab.get(sym1, 0)) + symtab.get(scoped_sym2, symtab.get(sym2, 0))
    else:
        try:
            value = int(operand)
        except ValueError:
            scoped_operand = f"{current_csect}.{operand}" if f"{current_csect}.{operand}" in symtab else operand
            value = symtab.get(scoped_operand, symtab.get(operand, 0))
    
    if label:
        scoped_label = f"{current_csect}.{label}"
        symtab[scoped_label] = value
        symtab_block[scoped_label] = current_block
        symtab_csect[scoped_label] = current_csect
    return 0  # EQU doesn't advance location counter

#PASS 1 - building the SYMTAB
def pass1(lines):
    symtab = {} #dictionary to hold labels and addresses (scoped by section.symbol)
    littab = {} #dictionary to hold literals and addresses
    start_address = 0 #default start at 0
    program_name = "NONAME"
    intermediate = [] #storing list of address, line tuples
    blocktab = {} #dictionary to hold block names (blocks/CSECT) and addresses and size
    current_block = 'DEFAULT'
    current_csect = 'DEFAULT'  # track current control section
    blocktab["DEFAULT"] = {"locctr":0, "address":0, "size":0}
    locctr = blocktab["DEFAULT"]["locctr"]
    symtab_block = {} #to track which block each symbol belongs to
    symtab_csect = {} #to track which CSECT each symbol belongs to
    # external definitions and references per current control section
    extdef = set()
    extref = set()

    first = parse_line(lines[0])
    if first and first['opcode'] == 'START':
        start_address = int(first['operand'])
        locctr = start_address 
        intermediate.append((5, locctr, first, current_block))
        lines = lines[1:]  

    for lineno, line in enumerate(lines, start=2):
        parsed = parse_line(line)
        if not parsed: 
            continue
        opcode = parsed['opcode']
        label = parsed['label']
        operand = parsed['operand']

        #handle control sections (CSECT) and USE directive for blocks
        if opcode == "CSECT":
            # CSECT starts a new control section - update current section
            # Use label as section name if present, otherwise use operand or generate
            if label:
                current_csect = label
            elif operand:
                current_csect = operand
            else:
                current_csect = f"CSECT_{lineno}"
            #create new block for this CSECT
            if current_csect not in blocktab:
                blocktab[current_csect] = {"locctr":0, "address":0, "size":0}
            #update previous block
            if current_block in blocktab:
                blocktab[current_block]["locctr"] = locctr
            #switch to new block (CSECT is also a block)
            current_block = current_csect
            locctr = blocktab[current_block]["locctr"]
            intermediate.append(((lineno-1)*5, locctr, parsed, current_block))
            continue
        
        if opcode == "USE":
            # USE directive for blocks within same CSECT
            if operand is None:
                operand = "DEFAULT"
            #create new block if doesn't exist
            block_key = f"{current_csect}_{operand}"
            if block_key not in blocktab:
                blocktab[block_key] = {"locctr":0, "address":0, "size":0}
            #update current block
            blocktab[current_block]["locctr"] = locctr
            #switch to new block
            current_block = block_key
            locctr = blocktab[current_block]["locctr"]

            intermediate.append(((lineno-1)*5, locctr, parsed, current_block))
            continue

        # assembler directives for linking
        if opcode == "EXTDEF":
            # comma-separated symbol names
            if operand:
                for name in [t.strip() for t in operand.split(',') if t.strip()]:
                    extdef.add(name)
            intermediate.append(((lineno-1)*5, locctr, parsed, current_block))
            continue
        if opcode == "EXTREF":
            if operand:
                for name in [t.strip() for t in operand.split(',') if t.strip()]:
                    extref.add(name)
            intermediate.append(((lineno-1)*5, locctr, parsed, current_block))
            continue

        #handle literals (=)
        if operand and operand.startswith('='):
            literal_name = operand
            if literal_name not in littab:
                littab[literal_name] = {
                "value": operand[1:],
                "address": None,
                "block": current_block
            }

        if label: 
            # Scope symbols by CSECT to allow duplicates across sections
            scoped_label = f"{current_csect}.{label}"
            if scoped_label in symtab:
                raise ValueError(f"Duplicate symbol: {label} in CSECT {current_csect}")
            # Store both scoped and unscoped versions
            # Scoped version is authoritative
            symtab[scoped_label] = locctr
            symtab_block[scoped_label] = current_block
            symtab_csect[scoped_label] = current_csect
            # Unscoped is just for convenience in local lookups
            # Don't error on unscoped duplicates across CSECTs - that's expected
            symtab[label] = locctr
            symtab_block[label] = current_block
            symtab_csect[label] = current_csect

        #format 4 handling (+)
        is_extended = False
        if opcode.startswith('+'):
            is_extended = True
            opcode = opcode[1:]
        
        if opcode in OPTAB:
            format = OPTAB[opcode]['format']
            if is_extended:
                locctr += 4
            elif "2" in format and not "3" in format: 
                locctr += 2
            else: 
                locctr += 3

        #DIRECTIVES
        elif opcode == "EQU":
            # EQU defines a symbol value without consuming space
            # Handle * (current location) and simple expressions
            if operand == '*':
                # Symbol equals current location
                pass  # label already set to locctr above
            elif '-' in operand:
                # Expression like BUFEND-BUFFER
                parts = operand.split('-')
                sym1, sym2 = parts[0].strip(), parts[1].strip()
                if sym1 in symtab and sym2 in symtab:
                    # Update symbol value to the difference
                    scoped_label = f"{current_csect}.{label}"
                    symtab[scoped_label] = symtab[sym1] - symtab[sym2]
                    symtab[label] = symtab[sym1] - symtab[sym2]
                # else: forward reference, skip for now (would need two-pass EQU handling)
            elif operand.isdigit():
                # Absolute value
                scoped_label = f"{current_csect}.{label}"
                symtab[scoped_label] = int(operand)
                symtab[label] = int(operand)
            # EQU doesn't advance locctr
        elif opcode == "WORD":
            locctr += 3 
        elif opcode == "RESW":
            # Auto-place literals before large reservations to keep them in PC-relative range
            res_size = 3 * int(operand)
            if res_size > 100:  # threshold for "large" reservation
                for literal in littab:
                    if littab[literal]["address"] is None:
                        littab[literal]["address"] = locctr
                        littab[literal]["block"] = current_block
                        if littab[literal]["value"].startswith('C\'') and littab[literal]["value"].endswith('\''):
                            locctr += len(littab[literal]["value"]) - 3
                        elif littab[literal]["value"].startswith('X\'') and littab[literal]["value"].endswith('\''):
                            locctr += (len(littab[literal]["value"]) - 3) // 2
                        else:
                            locctr += 3
            locctr += res_size
        elif opcode == "RESB":
            # Auto-place literals before large reservations to keep them in PC-relative range
            res_size = int(operand) if operand else 0
            if res_size > 100:  # threshold for "large" reservation
                for literal in littab:
                    if littab[literal]["address"] is None:
                        littab[literal]["address"] = locctr
                        littab[literal]["block"] = current_block
                        if littab[literal]["value"].startswith('C\'') and littab[literal]["value"].endswith('\''):
                            locctr += len(littab[literal]["value"]) - 3
                        elif littab[literal]["value"].startswith('X\'') and littab[literal]["value"].endswith('\''):
                            locctr += (len(littab[literal]["value"]) - 3) // 2
                        else:
                            locctr += 3
            locctr += res_size
        elif opcode == "BYTE":
            if operand.startswith('C\'') and operand.endswith('\''):
                locctr += len(operand) - 3
            elif operand.startswith('X\'') and operand.endswith('\''):
                locctr += (len(operand) - 3) // 2
            else:
                raise ValueError(f"Invalid BYTE operand: {operand}")

        elif opcode == "LTORG" or opcode == "END":
            for literal, data in littab.items():
                if data["address"] is None:
                    data["address"] = locctr
                    data["block"] = current_block

                    intermediate.append((
                        (lineno - 1) * 5,
                        locctr,
                        {"label": "*", "opcode": "BYTE", "operand": data["value"]},
                        current_block
                    ))

                    if data["value"].startswith("C'"):
                        locctr += len(data["value"]) - 3
                    elif data["value"].startswith("X'"):
                        locctr += (len(data["value"]) - 3) // 2
                    else:
                        locctr += 3

            if opcode == "END":
                intermediate.append(((lineno-1)*5, locctr, parsed, current_block))
                break
        blocktab[current_block]["locctr"] = locctr
        intermediate.append(((lineno-1)*5, locctr, parsed, current_block))
    
    blocktab[current_block]["locctr"] = locctr
    #get block sizes
    for block in blocktab:
        blocktab[block]["size"] = blocktab[block]["locctr"]
    
    # Assign block addresses
    # For CSECTs: each starts at 0 (relocatable)
    # For USE blocks within a CSECT: sequential after the CSECT's main block
    csects = set()
    for block in blocktab:
        # Extract CSECT name (before _ if it's a USE block)
        if '_' in block:
            csect_name = block.split('_')[0]
        else:
            csect_name = block
        csects.add(csect_name)
    
    # Assign addresses per CSECT
    for csect in sorted(csects):
        csect_blocks = [b for b in blocktab if b == csect or b.startswith(f"{csect}_")]
        # Main CSECT block starts at 0
        if csect in blocktab:
            blocktab[csect]["address"] = 0
        # USE blocks within CSECT are sequential
        addr = blocktab.get(csect, {}).get("size", 0) if csect in blocktab else 0
        for block in csect_blocks:
            if block != csect:  #skip main csect block, already set
                blocktab[block]["address"] = addr
                addr += blocktab[block]["size"]


    program_length = sum(block["size"] for block in blocktab.values())
    return (
    symtab, littab, intermediate, start_address, program_length,
    blocktab, symtab_block, sorted(extdef), sorted(extref),
    symtab_csect, program_name
    )


#Pass 2 Helper Functions
def generate_format2_code(code, operand, reg_codes):
    """Generate format 2 (2-byte register) object code."""
    tokens = [r.strip() for r in operand.split(',')] if operand else []
    r1 = tokens[0] if len(tokens) > 0 else '0'
    r2 = tokens[1] if len(tokens) > 1 else '0'
    obj = (code << 8) | (reg_codes.get(r1, 0) << 4) | reg_codes.get(r2, 0)
    return f"{obj:04X}"

def generate_format4_code(code, operand, symtab, extref):
    """Generate format 4 (4-byte extended) object code."""
    n, i, x, e = 1, 1, 0, 1
    b, p = 0, 0
    
    clean_operand = operand
    if operand.startswith('#'):
        n, i = 0, 1
        clean_operand = operand[1:]
    elif operand.startswith('@'):
        n, i = 1, 0
        clean_operand = operand[1:]
    
    if ',X' in clean_operand:
        x = 1
        clean_operand = clean_operand.replace(',X', '').strip()
    
    if clean_operand in symtab:
        target_addr = symtab[clean_operand]
    elif clean_operand in extref:
        target_addr = 0
    else:
        target_addr = 0
    
    obj = (code << 24) | (n << 25) | (i << 24) | (x << 23) | (b << 22) | (p << 21) | (e << 20) | (target_addr & 0xFFFFF)
    return f"{obj:08X}"

def calculate_pc_relative_disp(tloc, target_addr):
    """Calculate PC-relative displacement (from instruction + 3)."""
    return target_addr - (tloc + 3)

def select_smart_base(symtab, sym_addr, BASE_ADDR):
    """Select optimal BASE register value to bring symbol into range."""
    new_base = max(0, sym_addr - 2048)
    if (0 <= sym_addr - new_base <= 4095):
        return new_base
    return BASE_ADDR

def process_instruction_operand(operand, tloc, symtab, extref, BASE_ADDR, is_extended=False):
    """Process operand and calculate displacement for format 3/4 instructions.
    Returns: (disp, b_flag, p_flag, BASE_ADDR, sym)
    """
    n, i, x, b, p, e = 1, 1, 0, 1, 0, 0
    disp = 0
    sym = None
    
    # Handle literals
    if operand.startswith('='):
        literal = operand.strip()
        sym = literal
        # Handled separately in pass2
        return disp, b, p, BASE_ADDR, sym
    
    # Immediate addressing
    elif operand.startswith('#'):
        n, i = 0, 1
        sym = operand[1:]
        if sym.isdigit():
            disp = int(sym)
        else:
            disp = symtab.get(sym, 0) - (tloc + 3)
    
    # Indirect addressing
    elif operand.startswith('@'):
        n, i = 1, 0
        sym = operand[1:]
        disp = symtab.get(sym, 0) - (tloc + 3)
    
    # Simple or indexed addressing
    else:
        if ',X' in operand:
            x = 1
            operand = operand.replace(',X', '')
        sym = operand.strip()
        
        # Handle * (current location) with offset
        if sym.startswith('*'):
            if len(sym) > 1:
                offset = int(sym[1:])
            else:
                offset = 0
            target_addr = tloc + offset
            disp = target_addr - (tloc + 3)
            sym = None
        else:
            if sym in symtab:
                disp = symtab[sym] - (tloc + 3)
            elif sym in extref:
                disp = 0
            else:
                # Unknown symbol
                pass
    
    return disp, b, p, BASE_ADDR, sym

def apply_addressing_mode(disp, sym, symtab, BASE_ADDR, tloc, is_extended):
    """Apply PC-relative or base-relative addressing.
    Returns: (disp, b_flag, p_flag, BASE_ADDR)
    """
    b, p = 0, 1  # Default: PC-relative
    
    if sym and sym in symtab and not (-2048 <= disp <= 2047):
        # Out of PC-relative range
        if (0 <= symtab[sym] - BASE_ADDR <= 4095):
            # Base-relative works with current BASE
            b, p = 1, 0
            disp = symtab[sym] - BASE_ADDR
        else:
            # Try to find better BASE
            new_base = select_smart_base(symtab, symtab[sym], BASE_ADDR)
            if new_base != BASE_ADDR:
                BASE_ADDR = new_base
                b, p = 1, 0
                disp = symtab[sym] - BASE_ADDR
            else:
                raise ValueError(f"Displacement out of range for symbol: {sym}. Use + prefix for format 4 extended addressing.")
    
    return disp, b, p, BASE_ADDR

#PASS 2 - generating object code and object program 
def pass2(symtab, littab, intermediate, start_address, program_length, blocktab, symtab_block, extdef=None, extref=None, program_name="NONAME"):

    object_codes = []  # (tloc, obj_str, block)
    text_records = []
    mod_records = []  # M records: (addr, length, symbol)
    def_records = []  # D record entries: (name, addr)
    ref_records = []  # R record entries: names
    current_text = []
    current_start = None
    BASE_ADDR =0
    extdef = extdef or []
    extref = set(extref or [])
    emitted_literals = set()

    #fix symbtab addresses for blocks
    fixed_symtab = {}
    for sym, addr in symtab.items():
        blockname = symtab_block[sym]
        fixed_symtab[sym] = addr + blocktab[blockname]["address"]
    symtab = fixed_symtab

    for lineno, loc, line, block in intermediate: 
        opcode = line["opcode"]
        operand = line["operand"]

        #adjust locctr for blocks
        tloc = blocktab[block]["address"] + loc 



        is_extended = False
        if opcode.startswith('+'):
            is_extended = True
            opcode = opcode[1:]

        if opcode in OPTAB:
            if opcode == "BASE":
                BASE_ADDR = symtab[operand]
                continue

            entry = OPTAB[opcode]
            code = entry['opcode'] 
            format = entry['format']

            if "2" in format and not "3" in format:
                #Format 2, using 2 registers (8 bit op, 4 r1, 4 r2)
                #Register codes
                reg_codes = {'A': 0, 'X': 1, 'L': 2, 'B': 3, 'S': 4, 'T': 5, 'F': 6, '0': 0}
                tokens = [r.strip() for r in operand.split(',')] if operand else []
                r1 = tokens[0] if len(tokens) > 0 else '0'
                r2 = tokens[1] if len(tokens) > 1 else '0' #if there's no second register, use 0
                obj = (code << 8) | (reg_codes.get(r1, 0) << 4) | reg_codes.get(r2, 0)
                obj_str = f"{obj:04X}"
                object_codes.append((tloc, obj_str, block))
                if current_start is None:
                    current_start = tloc
                current_text.append(obj_str)
            
            else: 
                #format 3 
                n, i, x, b, p, e = 1, 1, 0, 1, 0, 0
                disp = 0

                if not operand: 
                    # RSUB or other no-operand instruction
                    obj = (code << 16) | (n << 17) | (i << 16) | (x << 15) | (b << 14) | (p << 13) | (e << 12)
                    obj_str = f"{obj:06X}"
                    object_codes.append((tloc, obj_str, block))
                    if current_start is None:
                        current_start = tloc
                    current_text.append(obj_str)
                    continue

                if is_extended:
                    e = 1
                    b = 0
                    p = 0  # Format 4 doesn't use PC-relative
                    
                    # Handle addressing modes
                    clean_operand = operand
                    if operand.startswith('#'):
                        n, i = 0, 1
                        clean_operand = operand[1:]
                    elif operand.startswith('@'):
                        n, i = 1, 0
                        clean_operand = operand[1:]
                    
                    if ',X' in clean_operand:
                        x = 1
                        clean_operand = clean_operand.replace(',X', '').strip()
                    
                    # Get target address
                    if clean_operand in symtab:
                        target_addr = symtab[clean_operand]
                    elif clean_operand in extref:
                        target_addr = 0  # External ref, will be fixed by loader
                    else:
                        target_addr = 0
                    
                    obj = (code << 24) | (n << 25) | (i << 24) | (x << 23) | (b << 22) | (p << 21) | (e << 20) | (target_addr & 0xFFFFF)
                    obj_str = f"{obj:08X}"
                else:

                    #handle literals
                    if operand.startswith('='):
                        literal = operand.strip()
                        lit = littab[literal]
                        literal_addr = lit["address"] + blocktab[lit["block"]]["address"]
                        disp = literal_addr - (tloc + 3)
                        if not (-2048 <= disp <= 2047):
                            if (0 <= (literal_addr - BASE_ADDR) <= 4095):
                                b = 1
                                p = 0
                                disp = literal_addr - BASE_ADDR
                            else:
                                # Try to find a better BASE
                                new_base = max(0, literal_addr - 2048)
                                if (0 <= literal_addr - new_base <= 4095):
                                    BASE_ADDR = new_base
                                    b = 1
                                    p = 0
                                    disp = literal_addr - BASE_ADDR
                                else:
                                    raise ValueError(f"Displacement out of range for literal: {literal}")
                        sym = literal

                    #immediate addressing
                    elif operand.startswith('#'):
                        n, i = 0, 1
                        sym = operand[1:]
                        if sym.isdigit():
                            disp = int(sym)
                        else: #PC relative
                            disp = symtab[sym] - (tloc + 3)
                    #indirect addressing
                    elif operand.startswith('@'):
                        n, i = 1, 0
                        sym = operand[1:]
                        disp = symtab[sym] - (tloc + 3)
                    else: #simple addressing
                        if ',X' in operand:
                            x = 1
                            operand = operand.replace(',X', '')
                        sym = operand.strip()
                        
                        # Handle * (current location) with offset: e.g., *-3, *+5
                        if sym.startswith('*'):
                            if len(sym) > 1:
                                offset = int(sym[1:])  # includes sign: *-3 → -3, *+5 → +5
                            else:
                                offset = 0
                            target_addr = tloc + offset
                            disp = target_addr - (tloc + 3)
                            sym = None  # no symbol lookup needed
                        else:
                            # Check if symbol exists before using it
                            if sym not in symtab and sym not in extref:
                                raise ValueError(f"Undefined symbol: {sym}")
                            if sym in symtab:
                                disp = symtab[sym] - (tloc + 3)
                            else:
                                # External reference - use 0 for now, M record will fix it
                                disp = 0
                
                    if sym and sym in symtab and not (-2048 <= disp <= 2047):
                        # Out of PC-relative range, try base-relative
                        if (0 <= symtab[sym] - BASE_ADDR <= 4095):
                            # Base-relative works with current BASE
                            b = 1
                            p = 0
                            disp = symtab[sym] - BASE_ADDR
                        else:
                            # Current BASE doesn't work, try to find a better one
                            # Find a BASE value that brings this symbol into range [0, 4095]
                            sym_addr = symtab[sym]
                            # Try setting BASE to sym_addr - 2048 (middle of 4KB range)
                            new_base = max(0, sym_addr - 2048)
                            if (0 <= sym_addr - new_base <= 4095):
                                # This BASE works for this symbol
                                BASE_ADDR = new_base
                                b = 1
                                p = 0
                                disp = sym_addr - BASE_ADDR
                            else:
                                # Even optimal BASE doesn't work, must use format 4
                                raise ValueError(f"Displacement out of range for symbol: {sym}. Use + prefix for format 4 extended addressing.")
                    elif not sym and not (-2048 <= disp <= 2047):
                        raise ValueError(f"Displacement out of range for * expression: {operand}")
                    
                    obj = (code << 16) | (n << 17) | (i << 16) | (x << 15) | (b << 14) | (p << 13) | (e << 12) | (disp & 0xFFF)
                    obj_str = f"{obj:06X}"
            # For format 4 externals, emit an M record
            if is_extended:
                target = operand.replace(',X','').replace('#','').replace('@','').strip() if operand else ''
                if target in extref:
                    # Address of the 20-bit field begins at tloc+1 (disp field in obj)
                    # Use 05 (20 bits) per SIC/XE convention
                    mod_records.append((tloc+1, 5, target))
            object_codes.append((tloc, obj_str, block))
            if current_start is None:
                current_start = tloc
            current_text.append(obj_str)

            #split text records if too long ( > 60 chars)
            if sum(len(x) for x in current_text) > 60:
                record = f"T{hexstr(current_start,6)}{hexstr(sum(len(x)//2 for x in current_text),2)}{''.join(current_text)}"
                text_records.append(record)
                current_text, current_start = [], None
        
        elif opcode == "BYTE" or opcode == "WORD":
            if opcode == "WORD":
                # Handle expressions in WORD operands
                if '-' in operand or '+' in operand:
                    # Expression: evaluate or handle externals
                    # Extract CSECT from block name (format: CSECT or CSECT_blockname)
                    csect_name = block.split('_')[0] if '_' in block else block
                    
                    parts = operand.replace('+', ' + ').replace('-', ' - ').split()
                    value = 0
                    has_external = False
                    op_sign = 1
                    
                    for part in parts:
                        if part == '+':
                            op_sign = 1
                        elif part == '-':
                            op_sign = -1
                        else:
                            # Check if symbol is external
                            sym_key = f"{csect_name}.{part}"
                            if part in extref:
                                # External symbol - generate M record
                                has_external = True
                                mod_records.append((tloc, 6, f"{'+' if op_sign == 1 else '-'}{part}"))
                            elif sym_key in symtab:
                                # Internal symbol
                                value += op_sign * symtab[sym_key]
                            elif part in symtab:
                                value += op_sign * symtab[part]
                            else:
                                # Try as constant
                                try:
                                    value += op_sign * int(part)
                                except ValueError:
                                    # Undefined symbol - use 0
                                    value += 0
                    
                    obj_str = f"{value & 0xFFFFFF:06X}"
                else:
                    # Simple constant
                    value = int(operand)
                    obj_str = f"{value:06X}"
            else: 
                if operand.startswith('C\'') and operand.endswith('\''):
                    chars = operand[2:-1]
                    obj_str = ''.join(f"{ord(c):02X}" for c in chars)
                elif operand.startswith('X\'') and operand.endswith('\''):
                    obj_str = operand[2:-1]
                else:
                    raise ValueError(f"Invalid BYTE operand: {operand}")
            object_codes.append((tloc, obj_str, block))
            if current_start is None:
                current_start = tloc
            current_text.append(obj_str)
        
        elif opcode == "RESW" or opcode == "RESB":
            if current_text:
                record = f"T{hexstr(current_start,6)}{hexstr(sum(len(x)//2 for x in current_text),2)}{''.join(current_text)}"
                text_records.append(record)
                current_text, current_start = [], None
        
        elif opcode == "LTORG" or opcode == "END":
            for literal, data in littab.items():
                if literal in emitted_literals:
                    continue

                if data["address"] is None:
                    continue

                abs_addr = data["address"] + blocktab[data["block"]]["address"]
                value = data["value"]

                if value.startswith("C'"):
                    chars = value[2:-1]
                    obj_str = ''.join(f"{ord(c):02X}" for c in chars)
                elif value.startswith("X'"):
                    obj_str = value[2:-1]
                else:
                    obj_str = f"{int(value):06X}"

                object_codes.append((address + blocktab[block]["address"], obj_str, block))
                emitted_literals.add(literal)
            if opcode == "END":
                break
    
    
    #Flush the last text record
    if current_text:
        record = f"T{hexstr(current_start,6)}{hexstr(sum(len(x)//2 for x in current_text),2)}{''.join(current_text)}"
        text_records.append(record)
    
    # Build D and R records
    for name in (extdef or []):
        if name in symtab:
            def_records.append((name, symtab[name]))
    for name in (extref or []):
        ref_records.append(name)

    header = f"H{program_name[:6]:<6}{hexstr(start_address,6)}{hexstr(program_length,6)}"
    records = [header]
    if def_records:
        # D followed by name(6) addr(6) pairs
        d_body = ''.join(f"{n:<6}{hexstr(a,6)}" for n,a in def_records)
        records.append(f"D{d_body}")
    if ref_records:
        r_body = ''.join(f"{n:<6}" for n in ref_records)
        records.append(f"R{r_body}")
    records.extend(text_records)
    # Add M records
    for addr, length, sym in mod_records:
        records.append(f"M{hexstr(addr,6)}{hexstr(length,2)}{sym:<6}")
    endrec = f"E{hexstr(start_address,6)}"
    records.append(endrec)

    return object_codes, records

def assemble_file(input_file):
    #pass 1
    lines = Path(input_file).read_text().splitlines()
    # preprocess: macro expansion
    lines = expand_macros(lines)
    symtab, littab, intermediate, start, length, blocktab, symtab_block, extdef, extref, symtab_csect, program_name = pass1(lines)

    #pass 2
    objcodes, objprogram = pass2(symtab, littab, intermediate, start, length, blocktab, symtab_block, extdef, extref, program_name)


    #write object program file
    Path("objectprogram.txt").write_text("\n".join(objprogram))

    #write listing file
    list_path = Path("listing.txt")
    listing_lines = [
        "Line  Loc   Source Statement            Object Code",
        "------------------------------------------------------"
    ]

    for lineno, loc, parsed, block in intermediate:
        label = parsed["label"] or ""
        opcode = parsed["opcode"] or ""
        operand = parsed["operand"] or ""
        # Calculate true location with block offset
        tloc = blocktab[block]["address"] + loc
        # Match by both location AND block to handle multiple CSECTs at same address
        obj = next((code for loc_code, code, code_block in objcodes if loc_code == tloc and code_block == block), "")
        # Safe string formatting with spacing
        source = f"{label} {opcode} {operand}".strip()
        line_str = f"{lineno:<5}  {hexstr(tloc,4)}  {source:<30} {obj}"
        listing_lines.append(line_str)

    list_path.write_text("\n".join(listing_lines))

    print("Assembly complete!")


if __name__ == "__main__":
    assemble_file("txt_files/control_section.txt")



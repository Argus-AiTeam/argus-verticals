module control_reference #(
    parameter integer COUNTER_WIDTH = 8,
    parameter integer WAIT_CYCLES = 0,
    parameter [31:0] BASE_ADDR = 32'h40001000
) (
    input wire PCLK, PRESETn, PSEL, PENABLE, PWRITE,
    input wire [31:0] PADDR, PWDATA,
    input wire [3:0] PSTRB,
    input wire [2:0] PPROT,
    output wire PREADY, PSLVERR, IRQ,
    output reg [31:0] PRDATA
);
    reg [1:0] control;
    reg [COUNTER_WIDTH-1:0] reload_value, count;
    reg pending, irq_mask;
    reg [31:0] scratch;
    reg [1:0] wait_count;
    wire [31:0] offset = PADDR - BASE_ADDR;
    wire selected = PSEL && PENABLE;
    assign PREADY = selected && (wait_count == WAIT_CYCLES);
    wire complete = PRESETn && selected && PREADY;
    wire mapped = offset == 0 || offset == 4 || offset == 8 ||
                  offset == 12 || offset == 16 || offset == 20;
    assign PSLVERR = complete && (!mapped || (PWRITE && offset == 8));
    wire commit_write = complete && PWRITE && !PSLVERR;
    wire event_tick = control[0] && (count == 0);
    wire clear_irq = commit_write && offset == 12 && PSTRB[0] && PWDATA[0];
    assign IRQ = pending && irq_mask;

    function [31:0] byte_mask(input [3:0] strobes);
        byte_mask = {{8{strobes[3]}}, {8{strobes[2]}}, {8{strobes[1]}}, {8{strobes[0]}}};
    endfunction
    wire [31:0] write_mask = byte_mask(PSTRB);
    wire [31:0] reload_extended = reload_value;

    always @* begin
        PRDATA = 0;
        if (complete && !PWRITE && !PSLVERR) begin
            case (offset)
                0: PRDATA = {30'b0, control};
                4: PRDATA = reload_value;
                8: PRDATA = count;
                12: PRDATA = {31'b0, pending};
                16: PRDATA = {31'b0, irq_mask};
                20: PRDATA = scratch;
                default: PRDATA = 0;
            endcase
        end
    end

    always @(posedge PCLK or negedge PRESETn) begin
        if (!PRESETn) begin
            control <= 0;
            reload_value <= 0;
            count <= 0;
            pending <= 0;
            irq_mask <= 0;
            scratch <= 0;
            wait_count <= 0;
        end else begin
            if (!selected || PREADY)
                wait_count <= 0;
            else
                wait_count <= wait_count + 1'b1;
            if (control[0]) begin
                if (count != 0)
                    count <= count - 1'b1;
                else if (control[1])
                    count <= reload_value;
                else
                    control[0] <= 0;
            end
            pending <= (pending && !clear_irq) || event_tick;
            if (commit_write) begin
                case (offset)
                    0: if (PSTRB[0]) begin
                        control <= PWDATA[1:0];
                        if (PWDATA[0])
                            count <= reload_value;
                    end
                    4: reload_value <= (reload_extended & ~write_mask) | (PWDATA & write_mask);
                    16: if (PSTRB[0]) irq_mask <= PWDATA[0];
                    20: scratch <= (scratch & ~write_mask) | (PWDATA & write_mask);
                    default: begin end
                endcase
            end
        end
    end
endmodule

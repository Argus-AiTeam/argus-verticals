module stream_fifo #(
    parameter WIDTH = 8,
    parameter DEPTH = 3,
    parameter PTR_WIDTH = DEPTH > 1 ? $clog2(DEPTH) : 1
) (
    input wire clk, reset,
    input wire in_valid,
    output wire in_ready,
    input wire [WIDTH-1:0] in_data,
    output wire out_valid,
    input wire out_ready,
    output wire [WIDTH-1:0] out_data
);
    reg [WIDTH-1:0] mem [0:DEPTH-1];
    reg [PTR_WIDTH-1:0] rd, wr;
    reg [PTR_WIDTH:0] count;
    wire pop = out_valid && out_ready;
    wire push = in_valid && in_ready;
    assign out_valid = !reset && count != 0;
    assign in_ready = !reset && (count < DEPTH || pop);
    assign out_data = mem[rd];
    initial begin
        if (WIDTH < 1 || DEPTH < 1 || PTR_WIDTH < (DEPTH > 1 ? $clog2(DEPTH) : 1))
            $fatal(1, "illegal FIFO parameters");
    end
    always @(posedge clk) begin
        if (reset) begin
            rd <= 0;
            wr <= 0;
            count <= 0;
        end else begin
            if (push) begin
                mem[wr] <= in_data;
                wr <= wr == DEPTH-1 ? 0 : wr+1'b1;
            end
            if (pop)
                rd <= rd == DEPTH-1 ? 0 : rd+1'b1;
            case ({push, pop})
                2'b10: count <= count+1'b1;
                2'b01: count <= count-1'b1;
                default: count <= count;
            endcase
        end
    end
endmodule

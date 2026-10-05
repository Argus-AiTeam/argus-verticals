module cdc_reference (
    input wire clk_src,
    input wire clk_dst,
    input wire arst_n,
    input wire level_in,
    output wire reset_src_n,
    output wire reset_dst_n,
    output wire level_out
);
    (* ASYNC_REG = "TRUE" *) reg [1:0] reset_src;
    (* ASYNC_REG = "TRUE" *) reg [1:0] reset_dst;
    always @(posedge clk_src or negedge arst_n)
        if (!arst_n) reset_src <= 2'b00;
        else reset_src <= {reset_src[0], 1'b1};
    always @(posedge clk_dst or negedge arst_n)
        if (!arst_n) reset_dst <= 2'b00;
        else reset_dst <= {reset_dst[0], 1'b1};
    assign reset_src_n = reset_src[1];
    assign reset_dst_n = reset_dst[1];

    reg launch;
    always @(posedge clk_src or negedge reset_src_n)
        if (!reset_src_n) launch <= 1'b0;
        else launch <= level_in;
    (* ASYNC_REG = "TRUE" *) reg [1:0] capture;
    always @(posedge clk_dst or negedge reset_dst_n)
        if (!reset_dst_n) capture <= 2'b00;
        else capture <= {capture[0], launch};
    assign level_out = capture[1];
endmodule

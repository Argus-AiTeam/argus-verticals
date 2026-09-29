module stream_fifo_tb;
    parameter WIDTH = 8, DEPTH = 3;
    reg clk = 0, reset = 1, in_valid = 0, out_ready = 0;
    reg [WIDTH-1:0] in_data = 0;
    wire in_ready, out_valid;
    wire [WIDTH-1:0] out_data;
    stream_fifo #(.WIDTH(WIDTH), .DEPTH(DEPTH)) dut(
        clk, reset, in_valid, in_ready, in_data, out_valid, out_ready, out_data
    );
    always #5 clk = !clk;
    reg [WIDTH-1:0] expected [0:8191];
    integer head = 0, tail = 0, occupancy = 0, sent = 0;
    integer reset_checks = 0, transfer_checks = 0, stall_checks = 0;
    integer full_checks = 0, empty_checks = 0, replace_checks = 0;
    integer seed;
    reg [31:0] rng;
    reg held = 0;
    reg [WIDTH-1:0] held_data;
    reg accepted;
    reg pending = 0;

    initial begin
        if (!$value$plusargs("SEED=%d", seed)) $fatal(1, "SEED required");
        rng = seed;
        for (integer cycle = 0; cycle < 1600; cycle = cycle+1) begin
            @(negedge clk);
            reset = cycle < 2 || cycle == 799 || cycle == 800;
            rng = rng * 1664525 + 1013904223;
            // Deterministic fill/drain windows guarantee boundary comparisons.
            in_valid = !reset && (pending || cycle % 100 < 30 || (cycle % 100 >= 60 && rng[8]));
            out_ready = !reset && (cycle % 100 >= 30 && (cycle % 100 < 60 || rng[20]));
            in_data = sent;
            @(posedge clk);
            if (reset) begin
                if (in_ready !== 0 || out_valid !== 0) $fatal(1, "reset handshake");
                occupancy = 0; head = tail; held = 0; pending = 0;
                reset_checks = reset_checks+1;
            end else begin
                if (out_valid !== (occupancy > 0)) $fatal(1, "valid mismatch");
                if (in_ready !== (occupancy < DEPTH || (occupancy > 0 && out_ready)))
                    $fatal(1, "ready mismatch");
                if (held && (!out_valid || out_data !== held_data)) $fatal(1, "unstable output");
                held = out_valid && !out_ready;
                held_data = out_data;
                if (held) stall_checks = stall_checks+1;
                if (occupancy == 0) empty_checks = empty_checks+1;
                if (occupancy == DEPTH) full_checks = full_checks+1;
                accepted = in_valid && in_ready;
                pending = in_valid && !in_ready;
                if (accepted && out_valid && out_ready) replace_checks = replace_checks+1;
                if (out_valid && out_ready) begin
                    if (out_data !== expected[head]) $fatal(1, "ordering/data mismatch");
                    head = head+1; occupancy = occupancy-1;
                    transfer_checks = transfer_checks+1;
                end
                if (accepted) begin
                    expected[tail] = in_data;
                    tail = tail+1; occupancy = occupancy+1; sent = sent+1;
                end
            end
        end
        $display("CHECK reset %0d", reset_checks);
        $display("CHECK transfer %0d", transfer_checks);
        $display("CHECK stall %0d", stall_checks);
        $display("CHECK full %0d", full_checks);
        $display("CHECK empty %0d", empty_checks);
        $display("CHECK replacement %0d", replace_checks);
        $display("PASS regression");
        $finish;
    end
endmodule

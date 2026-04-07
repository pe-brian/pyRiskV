#![no_std]
#![no_main]

#[no_mangle]
pub extern "C" fn _start() -> ! {
    unsafe {
        // n lu depuis 0x100 — configurable via JSON
        let n = core::ptr::read_volatile(0x100 as *const u32);
        // tableau à 0x400 — n entiers consécutifs
        let arr = 0x400 as *const u32;
        let mut sum: u32 = 0;
        let mut i: u32 = 0;

        while i < n {
            sum = sum.wrapping_add(
                core::ptr::read_volatile(arr.offset(i as isize))
            );
            i += 1;
        }

        core::arch::asm!(
            "mv a0, {0}",
            "li a7, 93",
            "ecall",
            in(reg) sum,
            options(noreturn)
        );
    }
}

#[panic_handler]
fn panic(_: &core::panic::PanicInfo) -> ! {
    loop {}
}
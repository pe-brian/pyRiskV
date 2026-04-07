#![no_std]
#![no_main]

#[no_mangle]
pub extern "C" fn _start() -> ! {
    unsafe {
        // n lu depuis 0x400 — initialisé par le JSON
        let n = core::ptr::read_volatile(0x400 as *const u32);
        let mut a: u32 = 0;
        let mut b: u32 = 1;
        let mut i: u32 = 0;

        while i < n {
            let tmp = a.wrapping_add(b);
            a = b;
            b = tmp;
            i += 1;
        }

        core::arch::asm!(
            "mv a0, {0}",
            "li a7, 93",
            "ecall",
            in(reg) b,
            options(noreturn)
        );
    }
}

#[panic_handler]
fn panic(_: &core::panic::PanicInfo) -> ! {
    loop {}
}
#![no_std]
#![no_main]

#[no_mangle]
static mut ARR: [u32; 8] = [64, 25, 12, 22, 11, 90, 3, 47];

#[no_mangle]
pub extern "C" fn _start() -> ! {
    unsafe {
        // N lu comme volatile — empêche le déroulage
        let n = core::ptr::read_volatile(0x500 as *const i32);
        let arr = &raw mut ARR as *mut u32;

        let mut i: i32 = 0;
        while i < n - 1 {
            let mut j: i32 = 0;
            while j < n - 1 - i {
                let a = core::ptr::read_volatile(arr.offset(j as isize));
                let b = core::ptr::read_volatile(arr.offset(j as isize + 1));
                if a > b {
                    core::ptr::write_volatile(arr.offset(j as isize), b);
                    core::ptr::write_volatile(arr.offset(j as isize + 1), a);
                }
                j += 1;
            }
            i += 1;
        }

        let result = core::ptr::read_volatile(arr);

        core::arch::asm!(
            "mv a0, {0}",
            "li a7, 93",
            "ecall",
            in(reg) result,
            options(noreturn)
        );
    }
}

#[panic_handler]
fn panic(_: &core::panic::PanicInfo) -> ! {
    loop {}
}
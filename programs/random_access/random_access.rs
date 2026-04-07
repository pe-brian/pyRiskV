#![no_std]
#![no_main]

#[no_mangle]
static DATA: [u32; 64] = [
      0,  10,  20,  30,  40,  50,  60,  70,
     80,  90, 100, 110, 120, 130, 140, 150,
    160, 170, 180, 190, 200, 210, 220, 230,
    240, 250, 260, 270, 280, 290, 300, 310,
    320, 330, 340, 350, 360, 370, 380, 390,
    400, 410, 420, 430, 440, 450, 460, 470,
    480, 490, 500, 510, 520, 530, 540, 550,
    560, 570, 580, 590, 600, 610, 620, 630,
];

#[no_mangle]
static INDICES: [u32; 64] = [
    23, 25,  7, 22, 45, 33, 19, 59,
    46,  9, 40, 18, 42, 31, 16, 21,
    36, 41, 29, 20, 11, 50, 39, 48,
     3, 30, 24, 55,  4, 57, 54, 49,
    10,  0, 60, 28, 44, 26, 52, 12,
    35, 53, 38, 32, 58, 13, 51, 62,
     2, 27, 37,  5, 34, 56, 43,  6,
    61,  8, 63, 15, 17, 47,  1, 14,
];

static N: i32 = 64;

#[no_mangle]
pub extern "C" fn _start() -> ! {
    unsafe {
        let n       = N;
        let data    = DATA.as_ptr();
        let indices = INDICES.as_ptr();
        let mut sum: u32 = 0;
        let mut i: i32   = 0;

        while i < n {
            let idx = core::ptr::read_volatile(indices.offset(i as isize));
            let val = core::ptr::read_volatile(data.offset(idx as isize));
            sum = sum.wrapping_add(val);
            i  += 1;
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
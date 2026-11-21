//! The Win32 calls Reidcc makes: full paths, PATH from the registry, the console, local time,
//! kill-on-close Job Objects (the proxy), Ctrl+C, and opening a file the way Explorer would.

use std::ffi::OsStr;
use std::os::windows::ffi::OsStrExt;
use windows_sys::Win32::Foundation::{CloseHandle, BOOL, HANDLE, TRUE};

pub fn wide(s: &str) -> Vec<u16> {
    OsStr::new(s).encode_wide().chain(std::iter::once(0)).collect()
}

pub fn full_path_name(p: &str) -> Option<String> {
    use windows_sys::Win32::Storage::FileSystem::GetFullPathNameW;
    let w = wide(p);
    let mut buf = vec![0u16; 1024];
    loop {
        let n = unsafe { GetFullPathNameW(w.as_ptr(), buf.len() as u32, buf.as_mut_ptr(), std::ptr::null_mut()) } as usize;
        if n == 0 {
            return None;
        }
        if n < buf.len() {
            return Some(String::from_utf16_lossy(&buf[..n]));
        }
        buf.resize(n + 1, 0);
    }
}

pub fn need_current_dir_for_exe(name: &str) -> bool {
    use windows_sys::Win32::System::Environment::NeedCurrentDirectoryForExePathW;
    unsafe { NeedCurrentDirectoryForExePathW(wide(name).as_ptr()) != 0 }
}

/// A string value (REG_SZ or REG_EXPAND_SZ), unexpanded.
fn reg_str(root: windows_sys::Win32::System::Registry::HKEY, key: &str, value: &str) -> Option<String> {
    use windows_sys::Win32::System::Registry::*;
    let (k, v) = (wide(key), wide(value));
    let flags = RRF_RT_REG_SZ | RRF_RT_REG_EXPAND_SZ | RRF_NOEXPAND;
    let mut size = 0u32;
    unsafe {
        if RegGetValueW(root, k.as_ptr(), v.as_ptr(), flags, std::ptr::null_mut(), std::ptr::null_mut(), &mut size) != 0 {
            return None;
        }
        let mut buf = vec![0u16; size as usize / 2 + 1];
        let mut size2 = (buf.len() * 2) as u32;
        if RegGetValueW(root, k.as_ptr(), v.as_ptr(), flags, std::ptr::null_mut(), buf.as_mut_ptr().cast(), &mut size2) != 0 {
            return None;
        }
        let end = buf.iter().position(|&c| c == 0).unwrap_or(buf.len());
        Some(String::from_utf16_lossy(&buf[..end]))
    }
}

/// A string value under HKEY_CURRENT_USER.
pub fn hkcu_str(key: &str, value: &str) -> Option<String> {
    reg_str(windows_sys::Win32::System::Registry::HKEY_CURRENT_USER, key, value)
}

/// The raw (unexpanded) Path value of the machine and user environments, machine first.
pub fn registry_paths() -> Vec<String> {
    use windows_sys::Win32::System::Registry::{HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE};
    [(HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"), (HKEY_CURRENT_USER, "Environment")]
        .into_iter().filter_map(|(root, key)| reg_str(root, key, "Path")).collect()
}

/// The user environment's raw Path value ("" when it has none).
pub fn user_path() -> String {
    hkcu_str("Environment", "Path").unwrap_or_default()
}

/// Write the user environment's Path, keeping the value's type (REG_EXPAND_SZ when there's none yet),
/// and tell running apps, so terminals opened from now on see it.
pub fn set_user_path(value: &str) -> bool {
    use windows_sys::Win32::System::Registry::*;
    use windows_sys::Win32::UI::WindowsAndMessaging::{SendMessageTimeoutW, HWND_BROADCAST, SMTO_ABORTIFHUNG, WM_SETTINGCHANGE};
    let (k, v, data) = (wide("Environment"), wide("Path"), wide(value));
    unsafe {
        let mut key: HKEY = std::ptr::null_mut();
        if RegOpenKeyExW(HKEY_CURRENT_USER, k.as_ptr(), 0, KEY_SET_VALUE | KEY_QUERY_VALUE, &mut key) != 0 {
            return false;
        }
        let mut ty = 0u32;
        let found = RegQueryValueExW(key, v.as_ptr(), std::ptr::null(), &mut ty, std::ptr::null_mut(), std::ptr::null_mut()) == 0;
        let ty = if found && ty == REG_SZ { REG_SZ } else { REG_EXPAND_SZ };
        let ok = RegSetValueExW(key, v.as_ptr(), 0, ty, data.as_ptr().cast(), (data.len() * 2) as u32) == 0;
        RegCloseKey(key);
        let env = wide("Environment");
        SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, env.as_ptr() as isize, SMTO_ABORTIFHUNG, 2000, std::ptr::null_mut());
        ok
    }
}

/// How many other processes run one of `names` (e.g. "reid.exe") from the folder `dir`.
pub fn running_in(dir: &str, names: &[&str]) -> usize {
    use windows_sys::Win32::System::Diagnostics::ToolHelp::*;
    use windows_sys::Win32::System::Threading::{OpenProcess, QueryFullProcessImageNameW, PROCESS_QUERY_LIMITED_INFORMATION};
    let (me, want) = (std::process::id(), crate::py::normcase(dir));
    let mut n = 0;
    unsafe {
        let snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
        if snap as isize == -1 {
            return 0;
        }
        let mut e: PROCESSENTRY32W = std::mem::zeroed();
        e.dwSize = std::mem::size_of::<PROCESSENTRY32W>() as u32;
        let mut more = Process32FirstW(snap, &mut e) != 0;
        while more {
            let len = e.szExeFile.iter().position(|&c| c == 0).unwrap_or(e.szExeFile.len());
            let exe = String::from_utf16_lossy(&e.szExeFile[..len]);
            if e.th32ProcessID != me && names.iter().any(|w| w.eq_ignore_ascii_case(&exe)) {
                let h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, e.th32ProcessID);
                if !h.is_null() {
                    let mut buf = [0u16; 1024];
                    let mut size = buf.len() as u32;
                    if QueryFullProcessImageNameW(h, 0, buf.as_mut_ptr(), &mut size) != 0
                        && crate::py::normcase(&crate::py::dirname(&String::from_utf16_lossy(&buf[..size as usize]))) == want {
                        n += 1;
                    }
                    CloseHandle(h);
                }
            }
            more = Process32NextW(snap, &mut e) != 0;
        }
        CloseHandle(snap);
    }
    n
}

pub fn local_time() -> (u16, u16, u16, u16, u16, u16) {
    use windows_sys::Win32::System::SystemInformation::GetLocalTime;
    let mut t = unsafe { std::mem::zeroed() };
    unsafe { GetLocalTime(&mut t) };
    (t.wYear, t.wMonth, t.wDay, t.wHour, t.wMinute, t.wSecond)
}

// -------------------------------------------------------------- console ---
use windows_sys::Win32::System::Console::*;

pub fn enable_vt() {
    unsafe {
        let h = GetStdHandle(STD_OUTPUT_HANDLE);
        let mut m = 0u32;
        if GetConsoleMode(h, &mut m) != 0 {
            SetConsoleMode(h, m | ENABLE_VIRTUAL_TERMINAL_PROCESSING);
        }
    }
}

pub type ConsoleModes = Vec<(HANDLE, u32)>;

pub fn console_save() -> ConsoleModes {
    let mut saved = vec![];
    for n in [STD_INPUT_HANDLE, STD_OUTPUT_HANDLE] {
        unsafe {
            let h = GetStdHandle(n);
            let mut m = 0u32;
            if GetConsoleMode(h, &mut m) != 0 {
                saved.push((h, m));
            }
        }
    }
    saved
}

/// Put the console modes back and drop keys typed while the session was ending.
pub fn console_restore(saved: &ConsoleModes) {
    unsafe {
        for (h, m) in saved {
            SetConsoleMode(*h, *m);
        }
        FlushConsoleInputBuffer(GetStdHandle(STD_INPUT_HANDLE));
    }
}

/// A console that a shell shares with us lists 2+ processes; one made just for us lists only us.
pub fn launched_from_terminal() -> bool {
    let mut procs = [0u32; 16];
    unsafe { GetConsoleProcessList(procs.as_mut_ptr(), 16) > 1 }
}

unsafe extern "system" fn ignore_ctrl_c(kind: u32) -> BOOL {
    (kind == CTRL_C_EVENT || kind == CTRL_BREAK_EVENT) as BOOL
}

/// Ctrl+C belongs to the session while it runs (not inherited by it, unlike a NULL handler).
pub fn ignore_ctrl_c_while(on: bool) {
    unsafe { SetConsoleCtrlHandler(Some(ignore_ctrl_c), if on { TRUE } else { 0 }) };
}

// ------------------------------------------------------------------ job ---
/// Put a suspended process in a kill-on-close Job Object, then resume it. mitmdump.exe starts
/// python.exe; starting suspended means that child is born in the job too. Returns the job.
pub fn job_kill_on_close(process: HANDLE) -> Option<HANDLE> {
    use windows_sys::Win32::System::JobObjects::*;
    #[link(name = "ntdll")]
    extern "system" {
        fn NtResumeProcess(h: HANDLE) -> i32;
    }
    let job = unsafe {
        let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
        let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        let ok = !job.is_null()
            && SetInformationJobObject(job, JobObjectExtendedLimitInformation, &info as *const _ as *const _,
                                       std::mem::size_of_val(&info) as u32) != 0
            && AssignProcessToJobObject(job, process) != 0;
        if ok { Some(job) } else {
            if !job.is_null() {
                CloseHandle(job);
            }
            None
        }
    };
    unsafe { NtResumeProcess(process) }; // always resume, job or not
    job
}

pub fn job_kill(job: HANDLE) {
    use windows_sys::Win32::System::JobObjects::TerminateJobObject;
    unsafe {
        TerminateJobObject(job, 0);
        CloseHandle(job);
    }
}

/// Is process `pid` still running? Access denied means it exists.
pub fn pid_alive(pid: u32) -> bool {
    use windows_sys::Win32::Foundation::{GetLastError, ERROR_ACCESS_DENIED, STILL_ACTIVE};
    use windows_sys::Win32::System::Threading::{GetExitCodeProcess, OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION};
    unsafe {
        let h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
        if h.is_null() {
            return GetLastError() == ERROR_ACCESS_DENIED;
        }
        let mut code = 0u32;
        let ok = GetExitCodeProcess(h, &mut code) != 0;
        CloseHandle(h);
        ok && code == STILL_ACTIVE as u32
    }
}

// ---------------------------------------------------------------- shell ---
/// os.startfile: open with the file's default program.
pub fn startfile(path: &str) {
    use windows_sys::Win32::UI::Shell::ShellExecuteW;
    use windows_sys::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL;
    let (op, p) = (wide("open"), wide(path));
    unsafe { ShellExecuteW(std::ptr::null_mut(), op.as_ptr(), p.as_ptr(), std::ptr::null(), std::ptr::null(), SW_SHOWNORMAL) };
}

/* Exercise a pending return while its caller's generated code is modified.
 * Runs directly on x86-64, and through the pinned Box64 on real ARM64 CI.
 * A passing run is not a reproduction or proof of the TazUO crash's cause.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

typedef int (*generated_fn)(void);
static unsigned char *caller, *churn;
static size_t page;
static int expected, callbacks;
enum { BLOCKS = 512, ROUNDS = 64, RESULT_OFFSET = 17 };

static void protect(void *p, size_t size, int flags) {
    if (mprotect(p, size, flags)) { perror("mprotect"); exit(3); }
}
static generated_fn function_at(void *p) {
    generated_fn result;
    _Static_assert(sizeof(result) == sizeof(p), "function pointer size");
    memcpy(&result, &p, sizeof(result));
    return result;
}
static void modify_caller(void) {
    ++callbacks;
    protect(caller, page, PROT_READ | PROT_WRITE | PROT_EXEC);
    memcpy(caller + RESULT_OFFSET, &expected, sizeof(expected));
    protect(caller, page, PROT_READ | PROT_EXEC);
    /* Compile many other blocks before returning into the invalidated caller.
     * Each round changes their immediates so prior translations are invalidated.
     */
    protect(churn, page * BLOCKS, PROT_READ | PROT_WRITE | PROT_EXEC);
    for (int n = 0; n < BLOCKS; ++n) {
        int token = expected + n;
        memcpy(churn + n * page + 1, &token, sizeof(token));
    }
    protect(churn, page * BLOCKS, PROT_READ | PROT_EXEC);
    for (int n = 0; n < BLOCKS; ++n)
        if (function_at(churn + n * page)() != expected + n) {
            fprintf(stderr, "FAIL churn round=%d block=%d\n", callbacks, n);
            exit(4);
        }
}
int main(void) {
    page = (size_t)sysconf(_SC_PAGESIZE);
    caller = mmap(NULL, page, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    churn = mmap(NULL, page * BLOCKS, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (caller == MAP_FAILED || churn == MAP_FAILED) { perror("mmap"); return 3; }
    /* push rbp; mov rbp,rsp; movabs rax,callback; call rax;
     * mov eax,result; pop rbp; ret. The callback preserves the frame pointer.
     */
    const unsigned char code[] = {0x55,0x48,0x89,0xe5,0x48,0xb8,
        0,0,0,0,0,0,0,0,0xff,0xd0,0xb8,0,0,0,0,0x5d,0xc3};
    memcpy(caller, code, sizeof(code));
    void (*callback)(void) = modify_caller;
    memcpy(caller + 6, &callback, sizeof(callback));
    for (int n = 0; n < BLOCKS; ++n) {
        churn[n * page] = 0xb8;
        churn[n * page + 5] = 0xc3;
    }
    protect(caller, page, PROT_READ | PROT_EXEC);
    protect(churn, page * BLOCKS, PROT_READ | PROT_EXEC);
    for (int round = 0; round < ROUNDS; ++round) {
        expected = 10000 + round * BLOCKS;
        int actual = function_at(caller)();
        if (actual != expected) {
            fprintf(stderr, "FAIL return round=%d expected=%d actual=%d\n", round, expected, actual);
            return 5;
        }
    }
    if (callbacks != ROUNDS) return 6;
    printf("BOX64_JIT_RETURN_OK rounds=%d generated_calls=%d\n", ROUNDS, ROUNDS * BLOCKS);
    munmap(caller, page); munmap(churn, page * BLOCKS);
    return 0;
}

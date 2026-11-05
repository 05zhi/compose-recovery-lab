/* Synthetic concurrent environment regression; no application or credentials. */
#define _GNU_SOURCE
#include <pthread.h>
#include <gnu/libc-version.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>

static atomic_int done;
static atomic_ulong reads;
static void *reader(void *unused) {
    (void)unused;
    while (!atomic_load_explicit(&done, memory_order_relaxed)) {
        const char *value = getenv("CRL_RACE_MISSING");
        if (value != NULL) abort();
        atomic_fetch_add_explicit(&reads, 1, memory_order_relaxed);
    }
    return NULL;
}
int main(void) {
    printf("glibc=%s\n", gnu_get_libc_version());
    fflush(stdout);
    struct rlimit no_core = {0, 0};
    setrlimit(RLIMIT_CORE, &no_core);
    pthread_t threads[4];
    for (int i = 0; i < 4; ++i)
        if (pthread_create(&threads[i], NULL, reader, NULL)) return 2;
    for (unsigned i = 0; i < 20000; ++i) {
        char name[48];
        snprintf(name, sizeof(name), "CRL_RACE_%08u", i);
        if (setenv(name, "synthetic-value", 1)) return 3;
    }
    atomic_store(&done, 1);
    for (int i = 0; i < 4; ++i) pthread_join(threads[i], NULL);
    unsigned long count = atomic_load(&reads);
    printf("completed=20000 reads=%lu\n", count);
    return count == 0 ? 4 : 0;
}

# The C++ back end, explained

This is a guided tour of the C++ Monte Carlo kernel for someone who knows Python and is
new to C++. It covers how Python calls the C++ code, where memory lives, which random
number generator is used and why, how fast the result is and why, and what would make it
faster. It ends with ten interview questions and short answers.

All timings quoted here were measured on the machine described in
[benchmarks/RESULTS.md](../benchmarks/RESULTS.md). Where a number comes from somewhere
else, the text says so and gives the command.

## 1. What the C++ back end is

The C++ code does one job: simulate price paths and keep running statistics. It does not
validate inputs, compute Black-Scholes prices or format results. Those steps happen once
per call, they are not where the time goes, and they stay in Python where all three back
ends share them.

A back end ("kernel") is anything that provides these two things:

```python
EuropeanSampler(spec, seed, antithetic)   # .advance(paths), .moments()
asian_moments(spec, steps, paths, seed, antithetic)
```

Both hand back six numbers: the count, the means of x and y, and the three centred sums
needed for their variances and covariance. Here y is the discounted payoff and x is the
discounted control variate. `derivkit/monte_carlo.py` turns those six numbers into a
price and a standard error, the same way for every back end.

The point of this split is that the back ends can only differ in the path loop. They
cannot disagree about what a control variate is or how a result is named.

## 2. Map of the code

| File | What it holds |
| --- | --- |
| `cpp/rng.hpp` | `NormalRng`: the random number generator. Header-only. |
| `cpp/welford.hpp` | `WelfordPair`: the running statistics. Header-only. |
| `cpp/monte_carlo.hpp` | Declarations: `VanillaSpec`, `EuropeanSampler`, `AsianSampler`. |
| `cpp/monte_carlo.cpp` | The two path loops. This is the code that runs hot. |
| `cpp/bindings.cpp` | The pybind11 glue that makes the above importable from Python. |
| `CMakeLists.txt` | Build recipe: compiler flags, where the built file goes. |
| `src/derivkit/_mc_cpp.py` | Python adapter: unpacks the spec, wraps the six numbers. |
| `src/derivkit/backends.py` | Chooses a kernel by name and explains missing ones. |

A few C++ ideas you will meet while reading:

- **Header (`.hpp`) and source (`.cpp`).** A header says what exists; a source file says
  how it works. Code in a header is visible to every file that includes it, which lets
  the compiler paste small functions directly into their callers ("inlining").
- **`namespace derivkit::mc { ... }`** is a named scope, like a Python module name. It
  stops these names clashing with anyone else's.
- **`const`** means "this will not change". It helps the reader and the compiler.
- **`struct` and `class`** are the same thing with different default visibility.
  `WelfordPair` is a struct because it is plain data; `EuropeanSampler` is a class
  because it hides its state.
- **Types are fixed at compile time.** `double` is a 64-bit float, the same as a Python
  float. `std::uint64_t` is an unsigned 64-bit integer.

## 3. How the binding works

### Building

`cmake --build build` compiles `bindings.cpp` and `monte_carlo.cpp` and links them into
one shared library:

```
src/derivkit/_mc_cpp_ext.cpython-313-darwin.so
```

A shared library is compiled machine code that a running program can load. The middle
part of the name says which Python it was built for; a different Python version needs a
rebuild. The file sits inside the package folder, so `import derivkit._mc_cpp_ext` finds
it like any other module.

### Importing

When Python imports the file, it looks inside for a function called
`PyInit__mc_cpp_ext` and calls it. The macro `PYBIND11_MODULE(_mc_cpp_ext, m)` in
`bindings.cpp` generates that function. The code in the macro's body runs once, at import
time, and registers what the module contains:

```cpp
py::class_<mc::EuropeanSampler>(m, "EuropeanSampler")   // a Python type backed by a C++ class
    .def(py::init(...))                                 // its constructor
    .def("advance", &mc::EuropeanSampler::advance, ...) // a method
    .def("moments", ...);
py::class_<mc::AsianSampler>(m, "AsianSampler") ...     // the same again for Asians
m.def("build_info", ...);                               // a plain function
```

pybind11 is a header-only C++ library. For each `.def` it generates a small wrapper
function that Python can call.

### One call, start to finish

Take `european(spec, McConfig(paths=1_000_000, seed=1), backend="cpp")`.

1. `monte_carlo.european` validates the spec and asks `backends.kernel("cpp")` for the
   kernel. That imports `_mc_cpp`, which imports the extension. If the extension is not
   built, the `ImportError` becomes a `BackendUnavailableError` with build instructions.
2. `_mc_cpp.EuropeanSampler(spec, seed, antithetic)` unpacks the spec into seven plain
   values and calls the extension's constructor.
3. pybind11's wrapper converts each Python value to its C++ type: `float` to `double`,
   `bool` to `bool`, `int` to `std::uint64_t`. A wrong type or a negative integer raises
   `TypeError` here, before any C++ of ours runs. It then creates the C++ object on the
   heap and stores a pointer to it inside a new Python object.
4. `sampler.advance(1_000_000)` goes through another wrapper. That wrapper releases
   Python's global interpreter lock (GIL), calls the C++ `advance`, and takes the lock
   back when it returns. This is the only step that takes meaningful time. For long
   runs the adapter makes this call repeatedly, about four million draws at a time (see
   "Ctrl-C" below).
5. `sampler.moments()` returns a C++ `std::tuple` of six numbers. pybind11 converts it to
   a Python tuple, and `_mc_cpp` wraps that in a `WelfordPair`.
6. `monte_carlo._finish_cv` computes the price and standard error from the six numbers.
7. When the Python sampler object is garbage collected, pybind11 deletes the C++ object.

Three things are worth noticing.

**The boundary is crossed once per few million paths, not once per path.** A crossing
costs far more than one path, so a design that called C++ once per path would throw away
most of the gain. An `advance(0)` call, which does nothing but cross the boundary and
come back, takes [[CROSSING]] (measured with `timeit` on `sampler.advance(0)`).

**Only plain numbers cross.** C++ never holds a reference to a Python object and Python
never sees a raw C++ pointer other than the sampler it owns. That removes the usual
sources of binding bugs: objects freed while still in use, and reference-count mistakes.

**Errors cross too.** If C++ throws `std::invalid_argument` (the Asian sampler's
constructor does this for zero steps), pybind11 catches it and raises `ValueError` in
Python.

### Why release the GIL in single-threaded code?

The GIL lets only one thread run Python code at a time. The C++ loop touches no Python
objects, so it does not need the lock. Releasing it does not make the simulation faster
and does not make it multi-threaded. It means that if the program has other Python
threads (a UI, a server), they keep running during a long simulation instead of freezing.

The price is a rule: one sampler belongs to one call. With the lock released, two threads
calling `advance` on the same sampler would corrupt it. The Python API never shares a
sampler, so this cannot happen through `european(...)`.

### Ctrl-C

Python only notices Ctrl-C between its own instructions. While a C++ function is running,
the interrupt waits. One C++ call for a billion paths would therefore ignore Ctrl-C for
many seconds, and a mistyped path count would have to be killed from outside.

So `_mc_cpp.py` does not make one call. It calls `advance` in slices of about four
million normal draws, a few hundredths of a second each, and Python checks for Ctrl-C
between slices. Because a sampler continues its random stream from one call to the next,
the result is identical to a single call; a test runs the same pricing with 37-draw
slices and compares. Both samplers are classes with an `advance` method for this reason:
a function that ran a whole simulation in one go could not be sliced.

## 4. Memory: where it is allocated, and why the inner loop allocates nothing

C++ has two places to put data.

- **The stack** holds a function's local variables. "Allocating" there means moving one
  pointer, and the memory is released automatically when the function returns.
- **The heap** is for data whose size is not known until run time or that must outlive
  the function. Getting heap memory means calling the allocator (`new`, or inside
  `std::vector`), which has to search for a free block. That is typically slower than
  simulating a whole path here, so it must not happen once per path.

Here is every allocation in a European pricing call:

| What | Where | When | Size |
| --- | --- | --- | --- |
| The `EuropeanSampler` object | heap | once, when Python constructs it | 2,616 bytes, 2,504 of them the generator's state |
| Local copy of the generator and statistics in `advance` | stack | once per `advance` call | same data, copied |
| `std::array<double, 256> z`, the block of normals | stack | once per `advance` call | 2 KB |
| The result tuple | Python heap | once, after the loop | 6 numbers |

Inside the loop itself there is nothing: no `new`, no `std::vector`, no `std::string`, no
Python objects. Each path reads one number from `z`, does arithmetic in CPU registers and
updates six numbers.

The pieces that make this work:

- **`std::mt19937_64` stores its state inline.** Its 312 words live inside the generator
  object, not behind a pointer to the heap. Copying the generator copies those bytes.
- **`std::array<double, 256>`** is a fixed-size array whose size is part of its type, so
  the compiler can reserve its space on the stack. `std::vector` would allocate on the
  heap.
- **Welford's update** keeps running statistics in six numbers. The samples themselves
  are never stored, so memory use does not grow with the number of paths. One billion
  paths use the same memory as one thousand.

The Asian sampler has exactly one heap allocation: its `std::vector<double> z_`, sized to
the number of fixings. That number is only known at run time, so it cannot be a
`std::array`. The vector is created once, in the sampler's constructor, and every path
reuses it. When the sampler is destroyed, the vector's destructor frees the memory
automatically. That pattern, where an object
owns a resource and releases it when it goes out of scope, is called RAII, and it is why
this code contains no `delete` and cannot leak.

The original C++ library got this wrong in one place: its antithetic Asian loop created a
new `std::vector` for every path. Moving that one line outside the loop is one of the
three fixes made when the old code was brought back.

For comparison, the pure-Python kernel allocates constantly. Every Python float is its
own heap object, so each `x - mean_x` creates one. The NumPy kernel allocates three work
arrays when the sampler is created and then reuses them through `out=` arguments, which
is the NumPy version of the same idea.

### Why `advance` copies its state into local variables

```cpp
NormalRng rng = rng_;      // copy the member into a local
WelfordPair acc = acc_;
... loop ...
rng_ = rng;                // write back once at the end
acc_ = acc;
```

The compiler cannot see inside `exp`, `log`, `sin` or `cos`; they live in the system
maths library. It has to assume such a call might modify any memory reachable from
outside the function, and the sampler object is reachable through `this`. So if the loop
used the members directly, the compiler would have to write them to memory before each
call and read them back after. A local variable whose address never leaves the function
cannot be touched by anyone else, so the compiler is free to keep it in a CPU register
for the whole loop.

## 5. The random number generator

**What:** `std::mt19937_64`, the 64-bit Mersenne Twister from the C++ standard library,
turned into normal draws by a hand-written Box-Muller transform.

**Why this one:** it is the generator the pure-Python engine already uses, and the goal
was interchangeable back ends. Because both back ends consume the same 64-bit integers in
the same order and do the same arithmetic on them, the same seed gives the same price.
The tests check that the C++ kernel reproduces 20 stored pure-Python results; on the
development machine the match is exact to the last bit, with Apple clang and with GCC.
That is a far stronger test than "the two agree within a few standard errors", and it is
what makes it safe to swap one back end for the other.

The details that make the match exact:

- **Seeding.** `std::mt19937_64 gen(seed)` uses a seeding recurrence fixed by the C++
  standard. The Python class implements the same recurrence.
- **Integer to uniform.** `static_cast<double>(u) * 0x1p-64` converts the integer to a
  double and scales by 2^-64. `0x1p-64` is a hexadecimal float literal for exactly 2^-64.
  Scaling by a power of two is exact, so this equals Python's `math.ldexp(float(u), -64)`.
  A zero is replaced by one first so that `log(u)` is never `log(0)`.
- **Box-Muller.** From two uniforms: `r = sqrt(-2 log u1)`, `theta = 2 pi u2`, and the two
  normals are `r cos(theta)` and `r sin(theta)`. The second is kept as a "spare" for the
  next request.
- **Blocks.** `fill` produces normals in pairs straight into a buffer, but in the same
  order as repeated single draws, including a spare left over from an earlier call.

**Why not `std::normal_distribution`?** The C++ standard fixes exactly which integers
`std::mt19937_64` produces, on every compiler. It does not fix how
`std::normal_distribution` turns them into normals, so GCC's library and Clang's library
give different numbers from the same seed. Writing the transform by hand is what makes
the stream portable.

**Is it a good generator?** For this job, yes. Its period is 2^19937 - 1 and it has been
a standard choice for Monte Carlo work for decades. It is known to fail a few specialised
tests of linear structure, which do not matter for pricing. It is not the fastest choice,
and that turns out to be the main story in section 7.

## 6. Floating point: one flag on, one flag deliberately off

**`-ffp-contract=off`.** Modern CPUs have a fused multiply-add instruction that computes
`a * b + c` with one rounding instead of two. Compilers may use it by default
("contraction"). The fused result is slightly more accurate, but it is a different number
in the last digit from what Python computes, because Python rounds after the multiply and
again after the add. With contraction on, an early test build disagreed with Python in
the 16th significant digit. Turning it off restored the exact match. It is not free: building
`benchmarks/where_time_goes.cpp` both ways with Apple clang gave about 24.9 ns per path
with contraction off and about 24.1 ns with it on, a cost of about 3%.

**No `-ffast-math`.** That flag lets the compiler assume floating-point arithmetic is
associative and that NaN and infinity never occur. It can reorder sums, which changes
results, and it breaks code that relies on IEEE behaviour. Welford's update is exactly
the kind of carefully ordered arithmetic that reordering would damage. The build uses
`-O3` and nothing from the fast-math family.

## 7. Is it faster? What the measurements say

Short version, from [benchmarks/RESULTS.md](../benchmarks/RESULTS.md):

| 10^7 paths, no variance reduction | python | numpy | cpp |
| --- | ---: | ---: | ---: |
| Run time, median (s) | 15.97 | 0.1174 | 0.2505 |
| Paths per second | 0.63 M | 85.19 M | 39.91 M |
| Price | 10.454013 | 10.455593 | 10.454013 |

Across all three path counts and all four variance-reduction settings:

- C++ runs the same paths 60.2 to 67.3 times faster than pure Python, and returns the
  same price for the same seed.
- C++ runs at 0.47 to 0.57 times the speed of NumPy. Put the other way round, NumPy is
  about 1.8 to 2.1 times faster than C++.
- NumPy is 109 to 137 times faster than pure Python.

So the honest summary is: **C++ beats pure Python by a wide margin, and loses to NumPy
by about a factor of two.**

### Where the time goes

These tables rebuild each kernel's loop one step at a time and report what each step
adds. They come from two small programs in `benchmarks/`, run in the same session as
RESULTS.md (so also on battery in Low Power Mode):

```bash
cmake --build build --target where_time_goes && ./build/where_time_goes
python benchmarks/where_time_goes.py
```

| C++ kernel, cost per path | ns |
| --- | ---: |
| mt19937_64 draw, converted to a uniform | 2.90 |
| Box-Muller transform (log, sqrt, sin, cos) | 11.61 |
| exp for the terminal price | 7.64 |
| payoff and Welford update | 2.81 |
| **whole kernel, one path** | **24.97** |
| whole kernel, one antithetic pair | 30.06 |
| not used: exp with log(S) inside the exponent | 2.14 |

| NumPy kernel, cost per path | ns |
| --- | ---: |
| PCG64 normal draw (standard_normal) | 6.42 |
| scale and shift (2 array passes) | 0.50 |
| exp of the whole array | 2.73 |
| payoff (2 array passes) | 0.80 |
| chunk moments (2 means, 2 centrings, 3 dots) | 1.29 |
| **whole kernel, one path** | **11.78** |
| whole kernel, one antithetic pair | 15.99 |

| Pure-Python kernel, cost per path | ns |
| --- | ---: |
| an empty loop iteration, for scale | 12.71 |
| mt19937_64 + Box-Muller normal draw | 1106.41 |
| exp and payoff | 218.14 |
| Welford update | 277.15 |
| **whole kernel, one path** | **1601.69** |
| whole kernel, one antithetic pair | 1824.76 |

These agree with RESULTS.md, where 10^7 paths take 0.2505 s in C++ (25.1 ns per path),
0.1174 s in NumPy (11.7 ns) and 15.97 s in pure Python (1,597 ns).

### Why C++ is so much faster than pure Python

The two do the same arithmetic on the same numbers. The difference is everything around
the arithmetic.

- In C++, `drift + vol_t * z` compiles to two machine instructions on values held in CPU
  registers.
- In Python, the same expression makes the interpreter look up each variable, check the
  type of each operand, find the right multiply and add functions for those types, call
  them, and allocate a new float object for each result. An empty loop iteration alone
  costs about half of what an entire C++ path costs.
- The gap is widest in the generator. The Mersenne Twister is integer bit-twiddling, and
  the pure-Python engine implements it with Python's arbitrary-size integers. That one
  step accounts for about two thirds of the pure-Python time.

### Why C++ is not faster than NumPy

NumPy's loops are also compiled code. A call like `np.exp(x, out=x)` runs a C loop over
the whole array, so NumPy pays the interpreter cost once per array operation rather than
once per path. With 65,536 paths per chunk, that cost disappears. So this is compiled
code against compiled code, and the winner is decided by what work each one does. The
tables show two differences, and neither is about the language.

1. **The normal draw.** The C++ kernel spends about 14.5 ns per normal: one Mersenne
   Twister draw plus Box-Muller's `log`, `sqrt`, `sin` and `cos`. NumPy spends about
   6.4 ns: its PCG64 generator feeds a ziggurat sampler, which needs no transcendental
   function for the great majority of draws. This alone is more than half of the gap.
2. **The `exp` call.** The C++ kernel computes `S * exp(drift + vol_t * z)`, exactly as
   the pure-Python engine does. The argument of `exp` is near zero and changes sign from
   path to path. The NumPy kernel moves the constants inside: `exp(log(df * S) + drift +
   vol_t * z)`, whose argument stays around 4.5. On this machine `exp` is about three and
   a half times faster in the second form (the last line of the C++ table measures it).
   A likely reason is that the library's `exp` takes a different branch depending on its
   argument, and a branch that flips at random is one the CPU cannot predict. That cause
   was not confirmed by profiling; the timing difference was measured.

Both advantages are available to C++ in principle. This kernel gives them up on purpose:
it must reproduce the pure-Python engine bit for bit, and that engine uses the Mersenne
Twister with Box-Muller and puts the spot outside the `exp`. The price of that guarantee
is roughly a factor of two against NumPy.

The remaining work, payoff plus statistics, costs about the same in both.

### What this means for accuracy per second

The error of a Monte Carlo price falls as one over the square root of the number of
paths. So a back end that is 2 times faster buys about 1.4 times less error in the same
time, and one that is 60 times faster buys about 8 times less.

Standard error reached in one second, from RESULTS.md:

| Variance reduction | python | numpy | cpp |
| --- | ---: | ---: | ---: |
| None | 1.85 x 10^-2 | 1.59 x 10^-3 | 2.32 x 10^-3 |
| Antithetic + control variate | 2.62 x 10^-3 | 2.45 x 10^-4 | 3.37 x 10^-4 |

Three things follow.

- **C++ against pure Python:** about 8 times less error in the same time.
- **C++ against NumPy:** about 1.4 to 1.5 times more error in the same time.
- **Variance reduction against no variance reduction:** about 6.5 to 7 times less error
  in the same time, in every back end. That is nearly as much as rewriting the loop in
  C++. Pure Python with both methods on (2.62 x 10^-3) is within 15% of C++ with
  neither (2.32 x 10^-3).

The control variate is free in running time: it reuses numbers the loop already has, and
paths per second do not change. Antithetic sampling costs a second `exp` per path, which
lowers paths per second by 12% in pure Python, 17% in C++ and 27% in NumPy. It roughly
halves the standard error for the same number of paths, so it still wins clearly: in one
second of C++, 1.27 x 10^-3 with it against 2.32 x 10^-3 without.

## 8. What I would change to go faster

In rough order of payoff. Only the items marked "measured" have numbers behind them from
this machine; the rest are standard techniques that were not built or timed here.

1. **Move `log(S)` inside the `exp`.** Measured for that step alone: it drops from about
   7.6 ns to about 2.1 ns. If the rest of the loop were unaffected, a path would go from
   about 25 ns to about 19.5 ns; the whole kernel was not rebuilt and timed that way. It
   is a one-line change. It costs bit-for-bit agreement with the pure-Python engine (the
   two would differ in the last few digits), which is why it was not made.
2. **Replace Box-Muller with a ziggurat or inverse-CDF sampler on a cheaper generator**
   such as xoshiro256++ or PCG64. Measured only indirectly: NumPy's sampler of this kind
   costs 6.4 ns per normal against 14.5 ns here. This gives up the shared stream with
   Python, so the two back ends would agree statistically instead of exactly.
3. **Compute the antithetic leg without a second `exp`.** The mirrored price is
   `S^2 exp(2 drift) / S_T`, one division instead of one `exp`. Not measured.
4. **Replace Welford's per-sample update with block sums.** The update does two divisions
   per path. Summing a block of centred values and merging blocks, as the NumPy kernel
   does, avoids them. The whole payoff-and-statistics step is under 3 ns, so the gain is
   small. Not measured.
5. **SIMD.** Process 2, 4 or 8 paths per instruction. The arithmetic vectorises easily;
   `exp` and `log` need a vector maths library, which the "standard library only" rule
   excludes. Not measured.
6. **Threads.** Paths are independent, so this scales almost linearly with cores. Each
   thread needs its own generator stream, and the per-thread statistics combine with the
   same merge formula the NumPy kernel uses. Excluded here so the comparison stays
   single-threaded.
7. **Allow fused multiply-add** by dropping `-ffp-contract=off`. Measured: about 3%
   (section 6). It costs bit-for-bit agreement with the pure-Python engine.
8. **`-march=native`.** Lets the compiler use every instruction the build machine has.
   Not measured; the result would no longer be portable to other CPUs.

With items 1 and 2 the C++ kernel would do the same work as the NumPy kernel, and the
comparison would then show what the language itself buys. That experiment was not run.

Two things that were tried during development and are already in the code:

- **Drawing normals in blocks** rather than one per path. In a throwaway test during
  development the block version took about 16% less time with Apple clang and about 20%
  less with GCC, with identical output. That test is not part of the repo.
- **Hoisting loop invariants.** The original code recomputed the drift, a square root and
  the discount factor for every path. They are now computed once.

## 9. Ten interview questions

**1. Your C++ is slower than NumPy. Why, and what did you learn?**
NumPy's inner loops are compiled C, so it was never interpreter against compiled code.
The gap is two algorithm choices: NumPy's ziggurat sampler is less than half the cost of
Box-Muller, and its `exp` runs on a friendlier argument. My kernel keeps the slower
choices because it must match the pure-Python engine bit for bit. The lesson is to
profile before assuming the language is the bottleneck: here the random numbers were.

**2. Why did you write Box-Muller by hand instead of using `std::normal_distribution`?**
The standard fixes the output of `std::mt19937_64` but not the algorithm inside
`std::normal_distribution`, so different standard libraries give different normals from
the same seed. A hand-written transform gives the same stream on every compiler and lets
me match the Python engine exactly.

**3. What does `-ffp-contract=off` do, and why not `-ffast-math`?**
It stops the compiler fusing `a * b + c` into one instruction with a single rounding.
The fused result differs from Python's in the last digit, which broke exact agreement.
`-ffast-math` goes much further: it lets the compiler reorder floating-point arithmetic
and assume no NaN or infinity, which changes results and can break numerically careful
code such as Welford's update.

**4. Where is memory allocated in the hot loop?**
Nowhere. The sampler is allocated once on the heap when Python creates it. Inside
`advance` the generator copy, the statistics and a 256-element `std::array` are on the
stack. The Asian sampler has one `std::vector`, allocated in its constructor and reused
by every path.

**5. Why copy member variables into locals at the top of `advance`?**
The compiler cannot see into `exp` or `log` and must assume they could modify anything
reachable through `this`, so members would be stored and reloaded around every call.
Locals whose address never escapes can stay in registers.

**6. What happens when Python calls `sampler.advance(n)`?**
pybind11's generated wrapper checks and converts `n` to `std::uint64_t`, releases the
GIL, calls the C++ method on the object the Python wrapper points to, re-acquires the
GIL and returns `None`. The adapter calls it once per few million paths, never once per
path, so the cost of crossing is negligible and Ctrl-C still gets through.

**7. Why release the GIL if the code is single-threaded? Is the sampler thread-safe?**
Releasing it lets other Python threads run during a long simulation; it does not speed
up the simulation. The sampler is not thread-safe: two threads advancing one sampler
would race on its state. Each pricing call creates its own sampler and never shares it.

**8. How do you know the C++ is correct?**
Three layers. It reproduces 20 stored pure-Python results to a relative tolerance of
1 x 10^-9, and exactly on the development machine with two compilers. Every back end must
land within 4 standard errors of the Black-Scholes closed form. And CI builds with GCC
and Clang and fails if any back end is missing rather than skipping its tests.

**9. What is Welford's algorithm and why use it?**
An update rule for the running mean and variance: `mean += (x - mean) / n`, and the sum
of squares grows by `(x - old_mean) * (x - new_mean)`. It needs constant memory, one
pass, and avoids the cancellation in `sum(x^2) - n * mean^2`, which loses digits when
the standard deviation is small compared with the mean. Its cost is a division per
update.

**10. How would you make this multi-threaded?**
Give each thread its own sampler with an independent stream, run `paths / threads` on
each, and merge the per-thread statistics with the pairwise form of Welford's update
(already in `WelfordPair.merge` on the Python side). The care points are independent
streams (distinct seeds are not a guarantee for the Mersenne Twister; a generator with
jump-ahead or a counter-based generator is cleaner), reproducibility (results should not
depend on the thread count), and keeping each thread's state on its own cache line.

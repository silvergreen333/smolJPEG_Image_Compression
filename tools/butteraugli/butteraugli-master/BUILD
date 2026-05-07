cc_library(
    name = "butteraugli_lib",
    srcs = [
        "butteraugli/butteraugli.cc",
        "butteraugli/butteraugli.h",
    ],
    hdrs = [
        "butteraugli/butteraugli.h",
    ],
    visibility = ["//visibility:public"],
)

cc_binary(
    name = "butteraugli",
    srcs = ["butteraugli/butteraugli_main.cc"],
    visibility = ["//visibility:public"],
    deps = [
        ":butteraugli_lib",
        "@jpeg_archive//:jpeg",
        "@png_archive//:png",
    ],
)

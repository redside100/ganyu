const cookies = Object.fromEntries(
  document.cookie.split(";").map((item) => {
    return item.trim().split("=", 2);
  })
);
console.log(`ltuid_v2: ${cookies['ltuid_v2']}`)
console.log(`ltoken_v2: ${cookies['ltoken_v2']}`)

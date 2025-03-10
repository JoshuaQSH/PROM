/*
Copyright (c) 2019, Ameer Haj Ali (UC Berkeley), and Intel Corporation
All rights reserved.
Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.
3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.
THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
*/
#include "header.h"

short input1[128];
short input2[128];
short input3[128];
int   ia[128] ALIGNED16;
int   ib[128] ALIGNED16;
int   ic[128] ALIGNED16;

__attribute__((noinline))
void example10b(short *__restrict__ input1, short *__restrict__ input2, short *__restrict__ input3, int* __restrict__ ia, int* __restrict__ ib, int* __restrict__ ic) {
  int i;
//#pragma clang loop vectorize_width(64) interleave_count(16)
//#pragma clang loop vectorize_width(64) interleave_count(16)
  for (i = 0; i < 128-1; i+=2) {
    ia[i] = (int) input1[i];
ia[i+1] = (int) input1[i+1];
    ib[i] = (int) input2[i];
ib[i+1] = (int) input2[i+1];
    ic[i] = (int) input3[i];
ic[i+1] = (int) input3[i+1];
  }
}
int main(int argc,char* argv[]){
  init_memory(&ia[0], &ia[128]);
  init_memory(&ib[0], &ib[128]);
  init_memory(&ic[0], &ic[128]);
  init_memory(&input1[0], &input1[128]);
  init_memory(&input2[0], &input2[128]);
  init_memory(&input3[0], &input3[128]);
  BENCH("Example10b", example10b(input1,input2,input3,ia,ib,ic), Mi*4/128*512, digest_memory(&ia[0], &ia[128])+digest_memory(&ib[0], &ib[128])+digest_memory(&ic[0], &ic[128]));
 
  return 0;
}
